"""Moonraker print ingestion, immutable state capture, and G-code inspection."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import pi
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from filament_manager.clients.moonraker import (
    MoonrakerClient,
    MoonrakerError,
    MoonrakerPrintState,
    MoonrakerSpoolPreflightState,
)
from filament_manager.config import get_settings
from filament_manager.domain.gcode_inspection import InspectionResult, inspect_gcode
from filament_manager.domain.profile_inheritance import settings_snapshot_from_profile
from filament_manager.domain.spool_preflight import (
    cura_material_guid,
    cura_product_material_guid,
)
from filament_manager.models.enums import (
    GcodeInspectionStatus,
    PrintJobStatus,
    ProfileStatus,
    SpoolStatus,
)
from filament_manager.models.inventory import (
    BuildPlate,
    BuildPlateSurface,
    FilamentProduct,
    MaterialProfile,
    Nozzle,
    Printer,
    Spool,
    SpoolUsageEvent,
)
from filament_manager.models.operations import ApplicationSetting
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.print_thumbnails import sanitize_print_thumbnail

MAX_INITIAL_HISTORY_JOBS = 10_000
HISTORY_PAGE_SIZE = 100
MASS_QUANTUM = Decimal("0.001")
logger = structlog.get_logger()


async def _capture_print_thumbnail(
    job: PrintJob,
    *,
    client: MoonrakerClient,
    filename: str,
    metadata: dict[str, Any],
) -> None:
    """Persist one sanitized thumbnail without making print ingestion depend on it."""

    if job.thumbnail_checked_at is not None:
        return
    if not isinstance(metadata.get("thumbnails"), list):
        return
    job.thumbnail_checked_at = datetime.now(UTC)
    try:
        downloaded = await client.gcode_thumbnail(filename, metadata)
        if downloaded is None:
            return
        thumbnail = sanitize_print_thumbnail(downloaded.data)
    except (MoonrakerError, ValueError):
        return
    job.thumbnail_data = thumbnail.data
    job.thumbnail_media_type = thumbnail.media_type
    job.thumbnail_sha256 = thumbnail.sha256
    job.thumbnail_width = thumbnail.width
    job.thumbnail_height = thumbnail.height


def _safe_file_metadata(metadata: dict[str, Any]) -> dict[str, object]:
    """Retain only bounded documented file facts useful to an operator."""

    result: dict[str, object] = {}
    for key in ("size", "modified", "object_height", "first_layer_height", "layer_count"):
        value = metadata.get(key)
        if isinstance(value, int | float | str) and not isinstance(value, bool):
            text = str(value)
            if len(text) <= 48:
                result[key] = value
    return result


def _timelapse_match_key(filename: str) -> str:
    """Normalize a G-code or video stem for conservative local association."""

    leaf = filename.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return re.sub(r"[^a-z0-9]+", "", leaf.casefold())[:180]


async def _associate_timelapses(
    session: AsyncSession,
    *,
    printer: Printer,
    client: MoonrakerClient,
) -> int:
    """Attach rendered Moonraker-timelapse MP4s without storing an external URL."""

    list_files = getattr(client, "timelapse_files", None)
    if list_files is None:
        return 0
    try:
        files = await list_files()
    except MoonrakerError:
        return 0
    candidates: list[tuple[str, str, datetime | None]] = []
    for item in files:
        path = item.get("path")
        if not isinstance(path, str):
            continue
        modified = _timestamp(item.get("modified"))
        candidates.append((path, _timelapse_match_key(path), modified))
    jobs = list(
        await session.scalars(
            select(PrintJob)
            .where(
                PrintJob.printer_id == printer.id,
                PrintJob.status != PrintJobStatus.IN_PROGRESS,
                PrintJob.timelapse_url.is_(None),
            )
            .order_by(PrintJob.ended_at.desc().nullslast())
            .limit(100)
        )
    )
    attached = 0
    for job in jobs:
        key = _timelapse_match_key(job.filename)
        if len(key) < 3:
            continue
        matches = [item for item in candidates if item[1] == key or item[1].startswith(key)]
        if job.ended_at is not None:
            timed = [
                item
                for item in matches
                if item[2] is None or abs((item[2] - job.ended_at).total_seconds()) <= 86_400
            ]
            matches = timed
        if not matches:
            continue
        matches.sort(
            key=lambda item: (
                abs((item[2] - job.ended_at).total_seconds())
                if item[2] is not None and job.ended_at is not None
                else float("inf"),
                item[0],
            )
        )
        job.timelapse_url = matches[0][0]
        job.record_version += 1
        attached += 1
    return attached


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
    profiles = list(
        await session.scalars(
            select(MaterialProfile)
            .where(
                MaterialProfile.printer_id == printer_id,
                MaterialProfile.status.in_((ProfileStatus.PUBLISHED, ProfileStatus.SUPERSEDED)),
            )
            .order_by(MaterialProfile.published_at.desc(), MaterialProfile.version.desc())
        )
    )
    expected = material_guid.casefold()
    # Preserve exact historical resolution for G-code sliced before stable
    # scope IDs were introduced, then resolve the current stable scope GUID.
    legacy = next(
        (profile for profile in profiles if cura_material_guid("product", profile.id) == expected),
        None,
    )
    if legacy is not None:
        return legacy
    return next(
        (
            profile
            for profile in profiles
            if profile.status == ProfileStatus.PUBLISHED
            and cura_product_material_guid(
                profile.filament_product_id,
                profile.printer_id,
                profile.nozzle_diameter_mm,
            )
            == expected
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
    nozzle = await session.get(Nozzle, printer.active_nozzle_id) if printer.active_nozzle_id else None
    cost_per_gram = (
        spool.purchase_cost / spool.nominal_net_mass_g
        if spool is not None and spool.purchase_cost is not None and spool.nominal_net_mass_g > 0
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
        "nozzle": (
            {
                "id": str(nozzle.id),
                "code": nozzle.nozzle_code,
                "diameter_mm": format(nozzle.diameter_mm, "f"),
                "material": nozzle.material,
                "coating": nozzle.coating,
            }
            if nozzle
            else None
        ),
        "spool": (
            {
                "id": str(spool.id),
                "code": spool.spool_code,
                "spoolman_id": spool.spoolman_id,
                "remaining_mass_g": format(spool.remaining_mass_effective_g, "f"),
                "cost_per_gram": format(cost_per_gram, "f") if cost_per_gram is not None else None,
                "currency": spool.currency if cost_per_gram is not None else None,
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


def _terminal_usage_targets(job: PrintJob) -> dict[UUID, tuple[Decimal, Decimal]]:
    """Return each exact spool's captured starting mass and total reported use."""

    targets: dict[UUID, tuple[Decimal, Decimal]] = {}
    for segment in sorted(job.segments, key=lambda item: item.segment_number):
        if segment.spool_id is None or segment.actual_filament_weight_g is None:
            continue
        used = segment.actual_filament_weight_g.quantize(MASS_QUANTUM)
        if used <= 0:
            continue
        snapshot_spool = segment.state_snapshot.get("spool")
        starting = (
            _decimal(snapshot_spool.get("remaining_mass_g")) if isinstance(snapshot_spool, dict) else None
        )
        if starting is None:
            continue
        previous = targets.get(segment.spool_id)
        targets[segment.spool_id] = (
            previous[0] if previous is not None else starting,
            (previous[1] if previous is not None else Decimal("0")) + used,
        )
    return targets


def _update_open_segment_usage(
    job: PrintJob,
    segment: PrintMaterialSegment,
    total_length_mm: Decimal,
) -> None:
    """Refresh the current segment from Moonraker's cumulative actual-use counter."""

    used_before = sum(
        (item.actual_filament_length_mm or Decimal("0"))
        for item in job.segments
        if item.id != segment.id and item.ended_at is not None
    )
    segment.actual_filament_length_mm = max(Decimal("0"), total_length_mm - used_before)
    segment.actual_filament_weight_g = _actual_weight_g(
        segment.actual_filament_length_mm,
        segment.state_snapshot,
    )


async def _apply_terminal_spool_usage(
    session: AsyncSession,
    *,
    job: PrintJob,
    correlation_id: str,
) -> None:
    """Apply actual terminal-job use once without double-counting prior Spoolman use.

    The immutable segment snapshot supplies the pre-print baseline. If Spoolman
    has already moved canonical inventory below that target, the lower trusted
    value wins and the zero adjustment still records that this job was handled.
    """

    if job.status not in {
        PrintJobStatus.COMPLETED,
        PrintJobStatus.CANCELLED,
        PrintJobStatus.FAILED,
    }:
        return
    now = datetime.now(UTC)
    for spool_id, (starting_mass, used_mass) in _terminal_usage_targets(job).items():
        usage_key = f"print:{job.id}:spool:{spool_id}"
        existing = await session.scalar(
            select(SpoolUsageEvent.id).where(
                SpoolUsageEvent.source == "moonraker_print",
                SpoolUsageEvent.idempotency_key == usage_key,
            )
        )
        if existing is not None:
            continue
        spool = await session.scalar(select(Spool).where(Spool.id == spool_id).with_for_update())
        if spool is None:
            continue
        target_remaining = max(Decimal("0"), starting_mass - used_mass).quantize(MASS_QUANTUM)
        before_effective = spool.remaining_mass_effective_g
        before_expected = spool.remaining_mass_expected_g
        corrected_remaining = min(before_effective, target_remaining)
        applied_delta = corrected_remaining - before_effective
        session.add(
            SpoolUsageEvent(
                spool_id=spool.id,
                source="moonraker_print",
                printer_id=job.printer_id,
                print_job_id=str(job.id),
                mass_delta_g=applied_delta,
                idempotency_key=usage_key,
                occurred_at=job.ended_at or now,
                created_at=now,
            )
        )
        spool.remaining_mass_expected_g = min(before_expected, target_remaining)
        spool.remaining_mass_effective_g = corrected_remaining
        spool.last_usage_event_at = job.ended_at or now
        spool.last_used_at = job.ended_at or now
        spool.first_used_at = spool.first_used_at or job.started_at or now
        spool.record_version += 1
        if corrected_remaining <= 0:
            spool.status = SpoolStatus.EMPTY
        elif corrected_remaining / spool.nominal_net_mass_g * Decimal("100") < Decimal(
            str(get_settings().sync.low_spool_threshold_percent)
        ):
            spool.status = SpoolStatus.LOW
        else:
            spool.status = SpoolStatus.IN_STOCK
        add_audit_event(
            session,
            actor_id=None,
            source="moonraker",
            action="spool.print_usage.apply",
            object_type="spool",
            object_id=spool.id,
            before={
                "remaining_mass_expected_g": str(before_expected),
                "remaining_mass_effective_g": str(before_effective),
            },
            after={
                "reported_actual_mass_g": str(used_mass),
                "remaining_mass_expected_g": str(spool.remaining_mass_expected_g),
                "remaining_mass_effective_g": str(spool.remaining_mass_effective_g),
                "print_status": job.status.value,
            },
            correlation_id=correlation_id,
        )
        if spool.spoolman_id is not None:
            add_outbox_job(
                session,
                job_type="spoolman.spool.adjust_weight",
                idempotency_key=f"spool:{spool.id}:print:{job.id}",
                aggregate_type="spool",
                aggregate_id=spool.id,
                aggregate_version=spool.record_version,
                payload={"spool_id": str(spool.id), "print_job_id": str(job.id)},
            )


def _apply_extracted(job: PrintJob, extracted: dict[str, object]) -> None:
    decimal_fields = (
        "nozzle_diameter_mm",
        "layer_height_mm",
        "line_width_mm",
        "extruder_temp_c",
        "bed_temp_c",
        "initial_bed_temp_c",
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
    session: AsyncSession,
    client: MoonrakerClient,
    *,
    filename: str,
    profile: MaterialProfile | None,
    material_guid: str,
    printer: Printer,
) -> tuple[InspectionResult | None, str | None, dict[str, Any], MaterialProfile | None, str]:
    metadata = await client.gcode_metadata(filename)
    try:
        gcode = await client.gcode_file(filename)
    except MoonrakerError:
        return None, None, metadata, profile, material_guid
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
    extracted_guid = str(result.extracted.get("material_guid") or "").strip().casefold()
    if profile is None and extracted_guid:
        profile = await _profile_for_guid(
            session,
            printer_id=printer.id,
            material_guid=extracted_guid,
        )
        if profile is not None:
            material_guid = extracted_guid
            result = inspect_gcode(
                metadata,
                gcode.header,
                gcode.tail,
                expected_profile=_json_safe(settings_snapshot_from_profile(profile)),
                expected_material_guid=material_guid,
                expected_machine_name=None,
            )
    return result, gcode.sha256, metadata, profile, material_guid


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
            nozzle_id=printer.active_nozzle_id,
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
            result, sha256, metadata, inspected_profile, inspected_guid = await _inspection_result(
                session,
                client,
                filename=print_state.filename,
                profile=profile,
                material_guid=material_guid,
                printer=printer,
            )
        except MoonrakerError:
            result, sha256, metadata, inspected_profile, inspected_guid = (
                None,
                None,
                {},
                profile,
                material_guid,
            )
        if profile is None and inspected_profile is not None:
            profile = inspected_profile
            requested_product = await session.get(FilamentProduct, profile.filament_product_id)
            job.material_profile_id = profile.id
            job.material_profile_version = profile.version
            job.filament_product_id = profile.filament_product_id
            job.material_guid = inspected_guid
            job.material_name = requested_product.product_name if requested_product else None
            job.material_type = requested_product.material_type if requested_product else None
            job.profile_snapshot = _json_safe(settings_snapshot_from_profile(profile))
            if isinstance(job.state_snapshot, dict):
                job.state_snapshot = {
                    **job.state_snapshot,
                    "profile": {
                        "id": str(profile.id),
                        "version": profile.version,
                        "status": profile.status.value,
                    },
                }
            for segment in job.segments:
                if segment.filament_product_id == profile.filament_product_id:
                    segment.material_profile_id = profile.id
                    segment.material_profile_version = profile.version
        job.gcode_sha256 = sha256
        job.moonraker_file_uuid = _bounded(metadata.get("uuid"), 96)
        await _capture_print_thumbnail(
            job,
            client=client,
            filename=print_state.filename,
            metadata=metadata,
        )
        if result is None:
            job.inspection_status = (
                GcodeInspectionStatus.BLOCKED if policy == "block" else GcodeInspectionStatus.UNAVAILABLE
            )
            job.inspection = {
                "mismatches": [],
                "warnings": ["Moonraker could not provide a safely bounded G-code inspection."],
                "printer_gate": (
                    "active" if preflight_state and preflight_state.phase == "inspecting" else "not_active"
                ),
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
            inspection_warnings = list(result.warnings)
            printer_gate = (
                "active" if preflight_state and preflight_state.phase == "inspecting" else "not_active"
            )
            if blocked and printer_gate == "not_active":
                inspection_warnings.append(
                    "A blocking condition was recorded, but the printer-side inspection gate was not active. "
                    "The sliced Cura start sequence must call FILAMENT_MANAGER_START_PRINT with the managed "
                    "material GUID before it calls the unchanged Klipper START_PRINT macro; this line does "
                    "not belong inside START_PRINT."
                )
            job.inspection = {
                "extracted": result.extracted,
                "mismatches": list(result.mismatches),
                "warnings": inspection_warnings,
                "file_metadata": _safe_file_metadata(metadata),
                "printer_gate": printer_gate,
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
            job.nozzle_id = printer.active_nozzle_id
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
                _update_open_segment_usage(job, open_segment, print_state.filament_used_mm)
                open_segment.ended_at = now
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
        if open_segment:
            _update_open_segment_usage(job, open_segment, print_state.filament_used_mm)
        if observed_status in terminal_statuses:
            job.status = observed_status
            job.ended_at = now
            if open_segment:
                open_segment.ended_at = now
        job.record_version += 1
        if observed_status in terminal_statuses:
            await _apply_terminal_spool_usage(
                session,
                job=job,
                correlation_id=correlation_id,
            )
        if job.thumbnail_checked_at is None:
            try:
                metadata = await client.gcode_metadata(print_state.filename)
            except MoonrakerError:
                pass
            else:
                await _capture_print_thumbnail(
                    job,
                    client=client,
                    filename=print_state.filename,
                    metadata=metadata,
                )
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
                "file_metadata": _safe_file_metadata(metadata),
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
    open_segment = next((segment for segment in reversed(job.segments) if segment.ended_at is None), None)
    if open_segment is not None and job.ended_at:
        open_segment.ended_at = job.ended_at
        if job.actual_filament_length_mm is not None:
            used_before = sum(
                (segment.actual_filament_length_mm or Decimal("0"))
                for segment in job.segments
                if segment.id != open_segment.id and segment.ended_at is not None
            )
            open_segment.actual_filament_length_mm = max(
                Decimal("0"), job.actual_filament_length_mm - used_before
            )
            open_segment.actual_filament_weight_g = _actual_weight_g(
                open_segment.actual_filament_length_mm,
                open_segment.state_snapshot,
            )
    await _apply_terminal_spool_usage(
        session,
        job=job,
        correlation_id=correlation_id,
    )
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
    skipped = 0
    latest_end = printer.last_print_history_end_at
    while start < MAX_INITIAL_HISTORY_JOBS:
        jobs = await client.history_jobs(start=start, limit=HISTORY_PAGE_SIZE, since=since)
        if not jobs:
            break
        for record_index, remote in enumerate(jobs, start=start):
            try:
                reconciled: PrintJob | None
                async with session.begin_nested():
                    reconciled = await _upsert_history_job(
                        session,
                        printer=printer,
                        remote=remote,
                        correlation_id=correlation_id,
                    )
                if reconciled is not None:
                    imported += 1
                    raw_metadata = remote.get("metadata")
                    history_metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
                    if reconciled.thumbnail_checked_at is None and not isinstance(
                        history_metadata.get("thumbnails"), list
                    ):
                        try:
                            history_metadata = await client.gcode_metadata(reconciled.filename)
                        except MoonrakerError:
                            history_metadata = {}
                    await _capture_print_thumbnail(
                        reconciled,
                        client=client,
                        filename=reconciled.filename,
                        metadata=history_metadata,
                    )
            except (InvalidOperation, TypeError, ValueError) as exc:
                # One malformed legacy Moonraker row must not poison every
                # subsequent history pass or prevent the success checkpoint.
                skipped += 1
                logger.warning(
                    "moonraker_print_history_record_skipped",
                    printer_code=printer.printer_code,
                    record_index=record_index,
                    error_class=type(exc).__name__,
                )
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
    await _associate_timelapses(session, printer=printer, client=client)
    await session.commit()
    if skipped:
        logger.warning(
            "moonraker_print_history_completed_with_skips",
            printer_code=printer.printer_code,
            skipped_records=skipped,
        )
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
