"""Moonraker print ingestion, immutable state capture, and G-code inspection."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import pi
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from filament_manager.clients.moonraker import (
    MoonrakerClient,
    MoonrakerError,
    MoonrakerPrintState,
    MoonrakerSpoolPreflightState,
)
from filament_manager.domain.gcode_inspection import InspectionResult, inspect_gcode
from filament_manager.domain.profile_inheritance import settings_snapshot_from_profile
from filament_manager.domain.spool_preflight import cura_material_guid
from filament_manager.models.enums import GcodeInspectionStatus, PrintJobStatus, ProfileStatus
from filament_manager.models.inventory import (
    BuildPlate,
    BuildPlateSurface,
    FilamentProduct,
    MaterialProfile,
    Printer,
    Spool,
)
from filament_manager.models.operations import ApplicationSetting
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.services.events import add_audit_event

MAX_INITIAL_HISTORY_JOBS = 10_000
HISTORY_PAGE_SIZE = 100


def _json_safe(value: object) -> dict[str, object]:
    """Round-trip a trusted snapshot into JSON-compatible scalar containers."""

    serialized = json.dumps(value, default=str, sort_keys=True)
    parsed = json.loads(serialized)
    return parsed if isinstance(parsed, dict) else {}


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _timestamp(value: object) -> datetime | None:
    parsed = _decimal(value)
    if parsed is None or parsed < 0:
        return None
    try:
        return datetime.fromtimestamp(float(parsed), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _bounded(value: object, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.replace("\x00", "").split())
    return normalized[:maximum] or None


def _history_status(value: object) -> PrintJobStatus:
    normalized = str(value or "").casefold()
    if normalized in {"complete", "completed"}:
        return PrintJobStatus.COMPLETED
    if normalized in {"cancelled", "canceled", "interrupted"}:
        return PrintJobStatus.CANCELLED
    if normalized in {"error", "failed"}:
        return PrintJobStatus.FAILED
    if normalized in {"in_progress", "printing", "paused"}:
        return PrintJobStatus.IN_PROGRESS
    return PrintJobStatus.LEGACY_UNKNOWN


async def gcode_inspection_policy(session: AsyncSession) -> str:
    """Return the persisted warn/block policy with a secure warn default."""

    setting = await session.scalar(
        select(ApplicationSetting).where(ApplicationSetting.key == "gcode_inspection")
    )
    policy = setting.value.get("policy") if setting else "warn"
    return str(policy) if policy in {"warn", "block"} else "warn"


async def _profile_for_guid(
    session: AsyncSession, *, printer_id: UUID, material_guid: str
) -> MaterialProfile | None:
    """Resolve a deterministic managed GUID without trusting it as a database key."""

    if not material_guid:
        return None
    profiles = await session.scalars(
        select(MaterialProfile).where(
            MaterialProfile.printer_id == printer_id,
            MaterialProfile.status.in_((ProfileStatus.PUBLISHED, ProfileStatus.SUPERSEDED)),
        )
    )
    return next(
        (
            profile
            for profile in profiles
            if cura_material_guid("product", profile.id) == material_guid.casefold()
        ),
        None,
    )


async def _latest_profile_for_product(
    session: AsyncSession, *, printer: Printer, filament_product_id: UUID
) -> MaterialProfile | None:
    profile: MaterialProfile | None = await session.scalar(
        select(MaterialProfile)
        .where(
            MaterialProfile.printer_id == printer.id,
            MaterialProfile.filament_product_id == filament_product_id,
            MaterialProfile.nozzle_diameter_mm == printer.nozzle_diameter_mm,
            MaterialProfile.status == ProfileStatus.PUBLISHED,
        )
        .order_by(MaterialProfile.version.desc())
        .limit(1)
    )
    return profile


async def _loaded_spool(
    session: AsyncSession, spoolman_id: int | None
) -> tuple[Spool | None, FilamentProduct | None]:
    if spoolman_id is None:
        return None, None
    spool = await session.scalar(select(Spool).where(Spool.spoolman_id == spoolman_id))
    product = await session.get(FilamentProduct, spool.filament_product_id) if spool else None
    return spool, product


async def _state_snapshot(
    session: AsyncSession,
    *,
    printer: Printer,
    spool: Spool | None,
    product: FilamentProduct | None,
    profile: MaterialProfile | None,
) -> dict[str, object]:
    plate = await session.get(BuildPlate, printer.active_plate_id) if printer.active_plate_id else None
    surface = (
        await session.get(BuildPlateSurface, printer.active_plate_surface_id)
        if printer.active_plate_surface_id
        else None
    )
    return {
        "printer": {
            "id": str(printer.id),
            "code": printer.printer_code,
            "name": printer.name,
            "nozzle_diameter_mm": format(printer.nozzle_diameter_mm, "f"),
            "nozzle_material": printer.nozzle_material,
        },
        "spool": (
            {
                "id": str(spool.id),
                "code": spool.spool_code,
                "spoolman_id": spool.spoolman_id,
                "remaining_mass_g": format(spool.remaining_mass_effective_g, "f"),
            }
            if spool
            else None
        ),
        "filament": (
            {
                "id": str(product.id),
                "material_type": product.material_type,
                "product_name": product.product_name,
                "color_name": product.color_name,
                "density_g_cm3": format(product.density_g_cm3, "f"),
                "diameter_mm": format(product.diameter_mm, "f"),
            }
            if product
            else None
        ),
        "profile": (
            {"id": str(profile.id), "version": profile.version, "status": profile.status.value}
            if profile
            else None
        ),
        "build_plate": (
            {"id": str(plate.id), "code": plate.plate_code, "name": plate.display_name} if plate else None
        ),
        "build_plate_surface": (
            {"id": str(surface.id), "code": surface.surface_code, "side": surface.side} if surface else None
        ),
        "captured_at": datetime.now(UTC).isoformat(),
    }


def _actual_weight_g(length_mm: Decimal | None, snapshot: dict[str, object]) -> Decimal | None:
    if length_mm is None:
        return None
    filament = snapshot.get("filament")
    if not isinstance(filament, dict):
        return None
    density = _decimal(filament.get("density_g_cm3"))
    diameter = _decimal(filament.get("diameter_mm"))
    if density is None or diameter is None:
        return None
    cross_section_mm2 = Decimal(str(pi)) * (diameter / Decimal("2")) ** 2
    return length_mm * cross_section_mm2 / Decimal("1000") * density


def _apply_extracted(job: PrintJob, extracted: dict[str, object]) -> None:
    decimal_fields = (
        "nozzle_diameter_mm",
        "layer_height_mm",
        "line_width_mm",
        "extruder_temp_c",
        "bed_temp_c",
        "chamber_temp_c",
        "print_speed_mm_s",
        "flow_percent",
        "retraction_distance_mm",
        "retraction_speed_mm_s",
        "pressure_advance",
        "predicted_filament_length_mm",
        "predicted_filament_weight_g",
        "estimated_duration_seconds",
    )
    for field in decimal_fields:
        if field in extracted:
            setattr(job, field, _decimal(extracted[field]))
    for field in (
        "slicer",
        "slicer_version",
        "cura_quality_profile",
        "material_name",
        "material_type",
        "machine_name",
        "material_guid",
    ):
        if field in extracted:
            setattr(job, field, _bounded(extracted[field], 255 if field != "material_guid" else 96))
    support = extracted.get("support_configuration")
    if isinstance(support, dict):
        job.support_configuration = _json_safe(support)


async def _inspection_result(
    client: MoonrakerClient,
    *,
    filename: str,
    profile: MaterialProfile | None,
    material_guid: str,
    printer: Printer,
) -> tuple[InspectionResult | None, str | None, dict[str, Any]]:
    metadata = await client.gcode_metadata(filename)
    try:
        gcode = await client.gcode_file(filename)
    except MoonrakerError:
        return None, None, metadata
    profile_snapshot = _json_safe(settings_snapshot_from_profile(profile)) if profile else None
    result = inspect_gcode(
        metadata,
        gcode.header,
        gcode.tail,
        expected_profile=profile_snapshot,
        expected_material_guid=material_guid or None,
        # Cura definition identifiers and operator-facing printer names are not
        # interchangeable. Retain the machine value as evidence; exact machine
        # enforcement remains the workstation deployment agent's responsibility.
        expected_machine_name=None,
    )
    return result, gcode.sha256, metadata


async def synchronize_live_print(
    session: AsyncSession,
    *,
    printer: Printer,
    client: MoonrakerClient,
    print_state: MoonrakerPrintState,
    preflight_state: MoonrakerSpoolPreflightState | None,
    correlation_id: str,
) -> PrintJob | None:
    """Capture or advance the current print and release a blocking gate safely."""

    if not print_state.filename or print_state.state == "standby":
        return None
    now = datetime.now(UTC)
    observed_status = _history_status(print_state.state)
    terminal_statuses = {
        PrintJobStatus.COMPLETED,
        PrintJobStatus.CANCELLED,
        PrintJobStatus.FAILED,
    }
    candidate_statuses = (
        (PrintJobStatus.IN_PROGRESS, observed_status)
        if observed_status in terminal_statuses
        else (PrintJobStatus.IN_PROGRESS,)
    )
    job = await session.scalar(
        select(PrintJob)
        .where(
            PrintJob.printer_id == printer.id,
            PrintJob.filename == print_state.filename,
            PrintJob.source == "live",
            PrintJob.status.in_(candidate_statuses),
        )
        .options(selectinload(PrintJob.segments))
        .order_by(PrintJob.created_at.desc())
        .limit(1)
    )
    if job is not None and job.status == observed_status and observed_status in terminal_statuses:
        return job
    spoolman_id = preflight_state.loaded_spool_id if preflight_state else None
    spool, product = await _loaded_spool(session, spoolman_id)
    material_guid = preflight_state.material_guid if preflight_state else ""
    profile = await _profile_for_guid(session, printer_id=printer.id, material_guid=material_guid)
    if profile is None and product is not None and not material_guid:
        profile = await _latest_profile_for_product(session, printer=printer, filament_product_id=product.id)
    requested_product = (
        await session.get(FilamentProduct, profile.filament_product_id)
        if profile is not None
        else product
        if not material_guid
        else None
    )

    if job is None:
        policy = await gcode_inspection_policy(session)
        physical_snapshot = await _state_snapshot(
            session, printer=printer, spool=spool, product=product, profile=profile
        )
        print_started = preflight_state is None or not preflight_state.start_pending
        snapshot = physical_snapshot if print_started else {**physical_snapshot, "capture_phase": "preflight"}
        profile_snapshot = _json_safe(settings_snapshot_from_profile(profile)) if profile else {}
        job = PrintJob(
            printer_id=printer.id,
            filename=print_state.filename,
            source="live",
            status=PrintJobStatus.IN_PROGRESS,
            spool_id=spool.id if spool and print_started else None,
            filament_product_id=(
                product.id
                if product and print_started
                else requested_product.id
                if requested_product
                else None
            ),
            material_profile_id=profile.id if profile else None,
            material_profile_version=profile.version if profile else None,
            build_plate_id=printer.active_plate_id,
            build_plate_surface_id=printer.active_plate_surface_id,
            nozzle_diameter_mm=printer.nozzle_diameter_mm,
            material_guid=material_guid or None,
            material_name=requested_product.product_name if requested_product else None,
            material_type=requested_product.material_type if requested_product else None,
            state_snapshot=snapshot,
            profile_snapshot=profile_snapshot,
            inspection_status=GcodeInspectionStatus.PENDING,
            inspection_policy=policy,
            inspection={},
            support_configuration={},
            started_at=now - timedelta(seconds=float(print_state.total_duration)),
            print_duration_seconds=print_state.print_duration,
            total_duration_seconds=print_state.total_duration,
        )
        session.add(job)
        await session.flush()
        if spool and print_started:
            session.add(
                PrintMaterialSegment(
                    print_job_id=job.id,
                    segment_number=1,
                    spool_id=spool.id,
                    filament_product_id=product.id if product else None,
                    material_profile_id=profile.id if profile else None,
                    material_profile_version=profile.version if profile else None,
                    source="print_start",
                    state_snapshot=physical_snapshot,
                    started_at=job.started_at or now,
                    created_at=now,
                )
            )
        try:
            result, sha256, metadata = await _inspection_result(
                client,
                filename=print_state.filename,
                profile=profile,
                material_guid=material_guid,
                printer=printer,
            )
        except MoonrakerError:
            result, sha256, metadata = None, None, {}
        job.gcode_sha256 = sha256
        job.moonraker_file_uuid = _bounded(metadata.get("uuid"), 96)
        if result is None:
            job.inspection_status = (
                GcodeInspectionStatus.BLOCKED if policy == "block" else GcodeInspectionStatus.UNAVAILABLE
            )
            job.inspection = {
                "mismatches": [],
                "warnings": ["Moonraker could not provide a safely bounded G-code inspection."],
            }
        else:
            _apply_extracted(job, result.extracted)
            blocked = policy == "block" and (profile is None or bool(result.mismatches))
            job.inspection_status = (
                GcodeInspectionStatus.BLOCKED
                if blocked
                else GcodeInspectionStatus.WARNING
                if result.mismatches or result.warnings
                else GcodeInspectionStatus.PASSED
            )
            job.inspection = {
                "extracted": result.extracted,
                "mismatches": list(result.mismatches),
                "warnings": list(result.warnings),
            }
        job.inspected_at = now
        add_audit_event(
            session,
            actor_id=None,
            source="moonraker",
            action="print.capture",
            object_type="print_job",
            object_id=job.id,
            before=None,
            after={
                "filename": job.filename,
                "inspection_status": job.inspection_status.value,
                "profile_id": str(job.material_profile_id) if job.material_profile_id else None,
            },
            correlation_id=correlation_id,
        )
        await session.commit()
        if preflight_state and preflight_state.phase == "inspecting":
            passed = job.inspection_status != GcodeInspectionStatus.BLOCKED
            await client.submit_gcode_inspection(passed=passed)
    else:
        job.print_duration_seconds = print_state.print_duration
        job.total_duration_seconds = print_state.total_duration
        job.actual_filament_length_mm = print_state.filament_used_mm
        job.actual_filament_weight_g = _actual_weight_g(print_state.filament_used_mm, job.state_snapshot)
        open_segment = next((segment for segment in reversed(job.segments) if segment.ended_at is None), None)
        print_started = preflight_state is None or not preflight_state.start_pending
        if print_started and not job.segments and spool:
            segment_profile = profile or await _latest_profile_for_product(
                session, printer=printer, filament_product_id=spool.filament_product_id
            )
            started_snapshot = await _state_snapshot(
                session,
                printer=printer,
                spool=spool,
                product=product,
                profile=segment_profile,
            )
            job.spool_id = spool.id
            job.filament_product_id = spool.filament_product_id
            job.material_profile_id = segment_profile.id if segment_profile else job.material_profile_id
            job.material_profile_version = (
                segment_profile.version if segment_profile else job.material_profile_version
            )
            job.build_plate_id = printer.active_plate_id
            job.build_plate_surface_id = printer.active_plate_surface_id
            job.state_snapshot = started_snapshot
            first_segment = PrintMaterialSegment(
                print_job_id=job.id,
                segment_number=1,
                spool_id=spool.id,
                filament_product_id=spool.filament_product_id,
                material_profile_id=segment_profile.id if segment_profile else None,
                material_profile_version=segment_profile.version if segment_profile else None,
                source="print_start",
                state_snapshot=started_snapshot,
                started_at=now,
                created_at=now,
            )
            session.add(first_segment)
            job.segments.append(first_segment)
            open_segment = first_segment
        if (open_segment.spool_id if open_segment else None) != (spool.id if spool else None):
            if open_segment:
                open_segment.ended_at = now
                used_before = sum(
                    (segment.actual_filament_length_mm or Decimal("0"))
                    for segment in job.segments
                    if segment.id != open_segment.id and segment.ended_at is not None
                )
                open_segment.actual_filament_length_mm = max(
                    Decimal("0"), print_state.filament_used_mm - used_before
                )
                open_segment.actual_filament_weight_g = _actual_weight_g(
                    open_segment.actual_filament_length_mm, open_segment.state_snapshot
                )
            if spool:
                segment_profile = await _latest_profile_for_product(
                    session, printer=printer, filament_product_id=spool.filament_product_id
                )
                segment_snapshot = await _state_snapshot(
                    session,
                    printer=printer,
                    spool=spool,
                    product=product,
                    profile=segment_profile,
                )
                next_segment = PrintMaterialSegment(
                    print_job_id=job.id,
                    segment_number=(max((item.segment_number for item in job.segments), default=0) + 1),
                    spool_id=spool.id,
                    filament_product_id=spool.filament_product_id,
                    material_profile_id=segment_profile.id if segment_profile else None,
                    material_profile_version=segment_profile.version if segment_profile else None,
                    source="m600",
                    state_snapshot=segment_snapshot,
                    started_at=now,
                    created_at=now,
                )
                job.segments.append(next_segment)
                open_segment = next_segment
        if observed_status in terminal_statuses:
            job.status = observed_status
            job.ended_at = now
            if open_segment:
                open_segment.ended_at = now
                used_before = sum(
                    (segment.actual_filament_length_mm or Decimal("0"))
                    for segment in job.segments
                    if segment.id != open_segment.id and segment.ended_at is not None
                )
                open_segment.actual_filament_length_mm = max(
                    Decimal("0"), print_state.filament_used_mm - used_before
                )
                open_segment.actual_filament_weight_g = _actual_weight_g(
                    open_segment.actual_filament_length_mm, open_segment.state_snapshot
                )
        job.record_version += 1
        await session.commit()
    return job


async def _upsert_history_job(
    session: AsyncSession,
    *,
    printer: Printer,
    remote: dict[str, Any],
    correlation_id: str,
) -> PrintJob | None:
    remote_id = _bounded(remote.get("job_id"), 160)
    filename = _bounded(remote.get("filename"), 512)
    if remote_id is None or filename is None:
        return None
    job = await session.scalar(
        select(PrintJob)
        .where(PrintJob.printer_id == printer.id, PrintJob.moonraker_job_id == remote_id)
        .options(selectinload(PrintJob.segments))
    )
    start_time = _timestamp(remote.get("start_time"))
    end_time = _timestamp(remote.get("end_time"))
    if job is None:
        job = await session.scalar(
            select(PrintJob)
            .where(
                PrintJob.printer_id == printer.id,
                PrintJob.filename == filename,
                PrintJob.moonraker_job_id.is_(None),
                PrintJob.source == "live",
            )
            .order_by(PrintJob.started_at.desc())
            .limit(1)
        )
    created = job is None
    raw_metadata = remote.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    if job is None:
        extracted_result = inspect_gcode(
            metadata,
            "",
            "",
            expected_profile=None,
            expected_material_guid=None,
            expected_machine_name=printer.name,
        )
        job = PrintJob(
            printer_id=printer.id,
            moonraker_job_id=remote_id,
            moonraker_file_uuid=_bounded(metadata.get("uuid"), 96),
            filename=filename,
            source="legacy_import",
            status=_history_status(remote.get("status")),
            nozzle_diameter_mm=_decimal(metadata.get("nozzle_diameter")) or printer.nozzle_diameter_mm,
            state_snapshot={
                "legacy_unresolved": True,
                "printer": {"id": str(printer.id), "code": printer.printer_code, "name": printer.name},
            },
            profile_snapshot={},
            inspection_status=GcodeInspectionStatus.UNAVAILABLE,
            inspection_policy="warn",
            inspection={
                "extracted": extracted_result.extracted,
                "mismatches": [],
                "warnings": ["Exact pre-0.2.1 material state could not be reconstructed."],
            },
            inspected_at=datetime.now(UTC),
            support_configuration={},
            started_at=start_time,
            ended_at=end_time,
        )
        _apply_extracted(job, extracted_result.extracted)
        session.add(job)
    else:
        job.moonraker_job_id = remote_id
        job.status = _history_status(remote.get("status"))
        job.started_at = start_time or job.started_at
        job.ended_at = end_time or job.ended_at
    job.actual_filament_length_mm = _decimal(remote.get("filament_used"))
    job.actual_filament_weight_g = _actual_weight_g(job.actual_filament_length_mm, job.state_snapshot)
    job.print_duration_seconds = _decimal(remote.get("print_duration"))
    job.total_duration_seconds = _decimal(remote.get("total_duration"))
    job.record_version += 0 if created else 1
    for segment in job.segments:
        if segment.ended_at is None and job.ended_at:
            segment.ended_at = job.ended_at
    if created:
        await session.flush()
        add_audit_event(
            session,
            actor_id=None,
            source="moonraker",
            action="print.history.import",
            object_type="print_job",
            object_id=job.id,
            before=None,
            after={"moonraker_job_id": remote_id, "source": job.source},
            correlation_id=correlation_id,
        )
    return job


async def synchronize_print_history(
    session: AsyncSession,
    *,
    printer: Printer,
    client: MoonrakerClient,
    correlation_id: str,
) -> int:
    """Import all available history once, then incrementally reconcile recent jobs."""

    initial = printer.print_history_initialized_at is None
    since = None
    if not initial and printer.last_print_history_end_at is not None:
        since = (printer.last_print_history_end_at - timedelta(seconds=1)).timestamp()
    start = 0
    imported = 0
    latest_end = printer.last_print_history_end_at
    while start < MAX_INITIAL_HISTORY_JOBS:
        jobs = await client.history_jobs(start=start, limit=HISTORY_PAGE_SIZE, since=since)
        if not jobs:
            break
        for remote in jobs:
            if await _upsert_history_job(
                session,
                printer=printer,
                remote=remote,
                correlation_id=correlation_id,
            ):
                imported += 1
            end_at = _timestamp(remote.get("end_time"))
            if end_at is not None and (latest_end is None or end_at > latest_end):
                latest_end = end_at
        if len(jobs) < HISTORY_PAGE_SIZE:
            break
        start += len(jobs)
    now = datetime.now(UTC)
    printer.print_history_initialized_at = printer.print_history_initialized_at or now
    printer.last_print_history_sync_at = now
    printer.last_print_history_end_at = latest_end
    await session.commit()
    return imported


async def profile_success_statistics(
    session: AsyncSession, profile_ids: list[UUID]
) -> dict[UUID, dict[str, object]]:
    """Return latest-assessment outcome counts for selected immutable profiles."""

    if not profile_ids:
        return {}
    from filament_manager.models.printing import PrintAssessment

    latest_revisions = (
        select(
            PrintAssessment.print_job_id,
            func.max(PrintAssessment.revision).label("revision"),
        )
        .group_by(PrintAssessment.print_job_id)
        .subquery()
    )
    rows = await session.execute(
        select(PrintJob.material_profile_id, PrintAssessment.rating, func.count(PrintAssessment.id))
        .join(PrintAssessment, PrintAssessment.print_job_id == PrintJob.id)
        .join(
            latest_revisions,
            (latest_revisions.c.print_job_id == PrintAssessment.print_job_id)
            & (latest_revisions.c.revision == PrintAssessment.revision),
        )
        .where(PrintJob.material_profile_id.in_(profile_ids))
        .group_by(PrintJob.material_profile_id, PrintAssessment.rating)
    )
    result: dict[UUID, dict[str, object]] = {}
    for profile_id, rating, count in rows:
        if profile_id is None:
            continue
        stats = result.setdefault(profile_id, {"rated_prints": 0, "ratings": {}})
        ratings = stats["ratings"]
        assert isinstance(ratings, dict)
        ratings[rating.value] = count
        previous_rated = stats["rated_prints"]
        assert isinstance(previous_rated, int)
        stats["rated_prints"] = previous_rated + count
    for stats in result.values():
        ratings = stats["ratings"]
        assert isinstance(ratings, dict)
        rated_value = stats["rated_prints"]
        assert isinstance(rated_value, int)
        rated = rated_value
        nonfailed = rated - int(ratings.get("failed", 0))
        stats["success_rate_percent"] = (
            format(Decimal(nonfailed) / Decimal(rated) * Decimal("100"), ".1f") if rated else None
        )
        stats["low_sample"] = rated < 5
    return result
