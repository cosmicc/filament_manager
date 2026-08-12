"""Dashboard, printers, integrations, audit, outbox, and future-device routes."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from filament_manager.clients.google_sheets import GoogleSheetsClient, GoogleSheetsError
from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.clients.spoolman import SpoolmanClient, SpoolmanError
from filament_manager.config import PrinterConfig, get_settings
from filament_manager.models.auth import User
from filament_manager.models.enums import JobStatus, SpoolStatus
from filament_manager.models.inventory import (
    BuildPlate,
    BuildPlateSurface,
    FilamentProduct,
    Printer,
    Spool,
)
from filament_manager.models.operations import AuditEvent, Device, OutboxJob
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.seed import seed_configured_system

from ..dependencies import Administrator, DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    BuildPlateResponse,
    BuildPlateSurfaceResponse,
    DashboardResponse,
    IntegrationStatus,
    PrinterResponse,
    PrinterUpdate,
)
from .inventory import spool_response

router = APIRouter(tags=["operations"])
SYSTEM_AGGREGATE_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _integration_statuses() -> list[IntegrationStatus]:
    settings = get_settings()
    checked_at = datetime.now(UTC)

    async def spoolman_status() -> IntegrationStatus:
        try:
            await SpoolmanClient(settings.spoolman).projection_health()
            return IntegrationStatus(
                service="Spoolman",
                status="connected",
                detail="API and managed projection fields ready",
                checked_at=checked_at,
            )
        except SpoolmanError:
            return IntegrationStatus(
                service="Spoolman",
                status="unavailable",
                detail="API or managed projection fields unavailable",
                checked_at=checked_at,
            )

    async def printer_status(printer_config: PrinterConfig) -> IntegrationStatus:
        try:
            await MoonrakerClient(printer_config).health()
            return IntegrationStatus(
                service=f"Moonraker · {printer_config.name}",
                status="connected",
                detail="Server reachable",
                checked_at=checked_at,
            )
        except MoonrakerError:
            return IntegrationStatus(
                service=f"Moonraker · {printer_config.name}",
                status="unavailable",
                detail="Server check failed",
                checked_at=checked_at,
            )

    async def google_status() -> IntegrationStatus:
        if not settings.google.enabled:
            return IntegrationStatus(
                service="Google Sheets",
                status="disabled",
                detail="Publication is disabled",
                checked_at=checked_at,
            )
        assert settings.google.spreadsheet_id
        try:
            await GoogleSheetsClient(
                settings.google.spreadsheet_id,
                settings.google.service_account_file,
                settings.google.resolved_service_account_info(),
            ).health()
            return IntegrationStatus(
                service="Google Sheets",
                status="connected",
                detail="Spreadsheet reachable",
                checked_at=checked_at,
            )
        except GoogleSheetsError:
            return IntegrationStatus(
                service="Google Sheets",
                status="unavailable",
                detail="API check failed",
                checked_at=checked_at,
            )

    checks = [spoolman_status(), google_status()]
    checks.extend(printer_status(printer) for printer in settings.moonraker.printers)
    return list(await asyncio.gather(*checks))


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(_: Viewer, session: DatabaseSession) -> DashboardResponse:
    """Return the operational first-view data without fake metrics."""

    total = await session.scalar(select(func.count(Spool.id)).where(Spool.archived.is_(False))) or 0
    needs = (
        await session.scalar(
            select(func.count(Spool.id)).where(
                Spool.status == SpoolStatus.NEEDS_WEIGHING, Spool.archived.is_(False)
            )
        )
        or 0
    )
    low = (
        await session.scalar(
            select(func.count(Spool.id)).where(Spool.status == SpoolStatus.LOW, Spool.archived.is_(False))
        )
        or 0
    )
    empty = (
        await session.scalar(
            select(func.count(Spool.id)).where(Spool.status == SpoolStatus.EMPTY, Spool.archived.is_(False))
        )
        or 0
    )
    active_result = await session.execute(
        select(Spool)
        .where(Spool.active_printer_id.is_not(None), Spool.archived.is_(False))
        .options(joinedload(Spool.filament_product).joinedload(FilamentProduct.vendor))
        .limit(1)
    )
    active_spool = active_result.unique().scalar_one_or_none()
    printer = await session.scalar(select(Printer).where(Printer.active_plate_id.is_not(None)).limit(1))
    plate = (
        await session.scalar(
            select(BuildPlate)
            .where(BuildPlate.id == printer.active_plate_id)
            .options(selectinload(BuildPlate.surfaces))
        )
        if printer
        else None
    )
    plate_surface = (
        await session.get(BuildPlateSurface, printer.active_plate_surface_id)
        if printer and printer.active_plate_surface_id
        else None
    )
    return DashboardResponse(
        total_spools=total,
        needs_weighing=needs,
        low_spools=low,
        empty_spools=empty,
        active_spool=spool_response(active_spool) if active_spool else None,
        active_plate=BuildPlateResponse.model_validate(plate) if plate else None,
        active_plate_surface=(
            BuildPlateSurfaceResponse.model_validate(plate_surface) if plate_surface else None
        ),
        integrations=await _integration_statuses(),
    )


@router.get("/printers", response_model=list[PrinterResponse])
async def list_printers(_: Viewer, session: DatabaseSession) -> list[Printer]:
    """List configured canonical printer state."""

    result = await session.execute(select(Printer).order_by(Printer.name))
    return list(result.scalars())


def _bounded_text(value: object, limit: int) -> str | None:
    """Return one safe single-line external value without exposing arbitrary payloads."""

    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("\r", " ").replace("\n", " ")
    return normalized[:limit] or None


def _positive_decimal_text(value: object) -> str | None:
    """Convert a finite positive external number to JSON-safe decimal text."""

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return format(parsed, "f")


def _axis_values(value: object) -> tuple[Decimal, Decimal, Decimal] | None:
    """Read the documented toolhead xyz vector while ignoring an optional E value."""

    if not isinstance(value, list | tuple) or len(value) < 3:
        return None
    try:
        values = tuple(Decimal(str(item)) for item in value[:3])
    except (InvalidOperation, TypeError):
        return None
    if not all(item.is_finite() for item in values):
        return None
    return values  # type: ignore[return-value]


def _discovered_printer_values(information: Any) -> dict[str, object]:
    """Extract the allowed canonical subset from Moonraker's documented responses."""

    configfile = information.object_status.get("configfile")
    settings = configfile.get("settings") if isinstance(configfile, dict) else None
    settings = settings if isinstance(settings, dict) else {}
    printer_settings = settings.get("printer")
    printer_settings = printer_settings if isinstance(printer_settings, dict) else {}
    extruder_settings = settings.get("extruder")
    extruder_settings = extruder_settings if isinstance(extruder_settings, dict) else {}
    kinematics = _bounded_text(printer_settings.get("kinematics"), 48)

    build_volume: dict[str, object] = {}
    toolhead = information.object_status.get("toolhead")
    toolhead = toolhead if isinstance(toolhead, dict) else {}
    axis_minimum = _axis_values(toolhead.get("axis_minimum"))
    axis_maximum = _axis_values(toolhead.get("axis_maximum"))
    if axis_minimum and axis_maximum:
        spans = tuple(maximum - minimum for minimum, maximum in zip(axis_minimum, axis_maximum, strict=True))
        if all(value > 0 for value in spans):
            build_volume = {
                "shape": "round" if kinematics == "delta" else "rectangular",
                "x_mm": format(spans[0], "f"),
                "y_mm": format(spans[1], "f"),
                "z_mm": format(spans[2], "f"),
            }
            if kinematics == "delta":
                build_volume["diameter_mm"] = format(min(spans[0], spans[1]), "f")

    values: dict[str, object] = {
        "kinematics": kinematics,
        "klipper_version": _bounded_text(information.printer_info.get("software_version"), 96),
        "moonraker_version": _bounded_text(information.server_info.get("moonraker_version"), 96),
        "host_name": _bounded_text(information.printer_info.get("hostname"), 255),
        "status": _bounded_text(information.printer_info.get("state"), 32) or "unknown",
    }
    nozzle = _positive_decimal_text(extruder_settings.get("nozzle_diameter"))
    if nozzle is not None:
        values["nozzle_diameter_mm"] = Decimal(nozzle)
    if build_volume:
        values["build_volume"] = build_volume
    return values


@router.patch("/printers/{printer_id}", response_model=PrinterResponse)
async def update_printer(
    printer_id: UUID,
    payload: PrinterUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> Printer:
    """Update manual printer metadata without exposing connection settings."""

    printer = await session.scalar(select(Printer).where(Printer.id == printer_id).with_for_update())
    if printer is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found")
    if printer.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "record_version_conflict", "Printer changed; reload")
    before: dict[str, object] = {
        "name": printer.name,
        "manufacturer": printer.manufacturer,
        "model": printer.model,
        "kinematics": printer.kinematics,
        "nozzle_diameter_mm": str(printer.nozzle_diameter_mm),
        "nozzle_material": printer.nozzle_material,
        "extruder_type": printer.extruder_type,
        "build_volume": printer.build_volume,
        "notes": printer.notes,
    }
    for field in (
        "name",
        "manufacturer",
        "model",
        "kinematics",
        "nozzle_material",
        "extruder_type",
        "notes",
    ):
        if field in payload.model_fields_set:
            value = getattr(payload, field)
            if field == "name" and value is None:
                raise ApiError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "printer_name_required",
                    "Printer name cannot be cleared",
                )
            setattr(printer, field, value.strip() or None if isinstance(value, str) else value)
    if payload.nozzle_diameter_mm is not None:
        printer.nozzle_diameter_mm = payload.nozzle_diameter_mm
    if payload.build_volume is not None:
        printer.build_volume = payload.build_volume
    printer.record_version += 1
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="printer.update",
        object_type="printer",
        object_id=printer.id,
        before=before,
        after={"name": printer.name, "record_version": printer.record_version},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return printer


@router.post("/printers/{printer_id}/synchronize-info", response_model=PrinterResponse)
async def synchronize_printer_information(
    printer_id: UUID,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> Printer:
    """Refresh useful printer metadata from documented Moonraker/Klipper fields."""

    printer = await session.get(Printer, printer_id)
    if printer is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found")
    configured = next(
        (item for item in get_settings().moonraker.printers if item.id == printer.printer_code),
        None,
    )
    if configured is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "printer_not_configured",
            "Printer does not have a matching Moonraker configuration",
        )
    await session.rollback()
    try:
        information = await MoonrakerClient(configured).printer_information()
    except MoonrakerError as exc:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "moonraker_printer_sync_failed",
            "Moonraker printer information synchronization failed",
        ) from exc
    values = _discovered_printer_values(information)
    synced_printer: Printer | None = await session.scalar(
        select(Printer).where(Printer.id == printer_id).with_for_update()
    )
    if synced_printer is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found")
    before: dict[str, object] = {
        "kinematics": synced_printer.kinematics,
        "nozzle_diameter_mm": str(synced_printer.nozzle_diameter_mm),
        "klipper_version": synced_printer.klipper_version,
        "moonraker_version": synced_printer.moonraker_version,
        "build_volume": synced_printer.build_volume,
    }
    for field, value in values.items():
        if value is not None:
            setattr(synced_printer, field, value)
    now = datetime.now(UTC)
    synced_printer.last_seen_at = now
    synced_printer.last_info_sync_at = now
    synced_printer.record_version += 1
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="moonraker",
        action="printer.synchronize_info",
        object_type="printer",
        object_id=synced_printer.id,
        before=before,
        after={
            "kinematics": synced_printer.kinematics,
            "nozzle_diameter_mm": str(synced_printer.nozzle_diameter_mm),
            "klipper_version": synced_printer.klipper_version,
            "moonraker_version": synced_printer.moonraker_version,
            "build_volume": synced_printer.build_volume,
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return synced_printer


@router.post("/system/seed")
async def seed_configured_resources(
    request: Request, administrator: Administrator, session: DatabaseSession
) -> dict[str, int]:
    """Seed missing server-configured printers and build plates from validated settings."""

    seeded = await seed_configured_system(session, get_settings())
    if seeded["plates"] or seeded["printers"]:
        add_audit_event(
            session,
            actor_id=administrator.id,
            source="web",
            action="system.seed.web",
            object_type="system",
            object_id=None,
            before=None,
            after={"plates": seeded["plates"], "printers": seeded["printers"]},
            correlation_id=request.state.correlation_id,
        )
    await session.commit()
    return seeded


@router.get("/integrations/status", response_model=list[IntegrationStatus])
async def integration_status(_: Viewer) -> list[IntegrationStatus]:
    """Check configured external APIs without exposing their URLs or secrets."""

    return await _integration_statuses()


async def _queue_system_job(
    *,
    job_type: str,
    request: Request,
    operator: User,
    session: DatabaseSession,
) -> dict[str, str]:
    version = int(datetime.now(UTC).timestamp() * 1_000_000)
    add_outbox_job(
        session,
        job_type=job_type,
        idempotency_key=f"{job_type}:{version}",
        aggregate_type="system",
        aggregate_id=SYSTEM_AGGREGATE_ID,
        aggregate_version=version,
        payload={},
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action=f"{job_type}.requested",
        object_type="system",
        object_id=None,
        before=None,
        after=None,
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"status": "queued"}


@router.post("/integrations/spoolman/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def reconcile_spoolman(
    request: Request, operator: Operator, session: DatabaseSession
) -> dict[str, str]:
    """Queue a complete API-only Spoolman reconciliation."""

    return await _queue_system_job(
        job_type="spoolman.reconcile.full", request=request, operator=operator, session=session
    )


@router.post("/integrations/google/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish_google(request: Request, operator: Operator, session: DatabaseSession) -> dict[str, str]:
    """Queue a coalescible Google publication pass."""

    return await _queue_system_job(
        job_type="google.publish.pending", request=request, operator=operator, session=session
    )


@router.post("/integrations/google/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild_google(
    request: Request, administrator: Administrator, session: DatabaseSession
) -> dict[str, str]:
    """Queue a deterministic full protected-workbook rebuild."""

    return await _queue_system_job(
        job_type="google.rebuild.full",
        request=request,
        operator=administrator,
        session=session,
    )


@router.get("/jobs", response_model=list[dict[str, object]])
async def list_jobs(
    _: Viewer,
    session: DatabaseSession,
    job_status: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    """Inspect bounded outbox state without exposing full payloads or secrets."""

    query = select(OutboxJob).order_by(OutboxJob.created_at.desc()).limit(min(max(limit, 1), 200))
    if job_status:
        try:
            query = query.where(OutboxJob.status == JobStatus(job_status))
        except ValueError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_status", "Unknown job status"
            ) from exc
    result = await session.execute(query)
    return [
        {
            "id": job.id,
            "job_type": job.job_type,
            "aggregate_type": job.aggregate_type,
            "aggregate_id": job.aggregate_id,
            "aggregate_version": job.aggregate_version,
            "status": job.status.value,
            "attempts": job.attempts,
            "next_attempt_at": job.next_attempt_at,
            "last_error_class": job.last_error_class,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
        }
        for job in result.scalars()
    ]


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    job_id: UUID,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Reset one failed/dead job for an explicit administrator retry."""

    job = await session.scalar(select(OutboxJob).where(OutboxJob.id == job_id).with_for_update())
    if job is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_job", "Job not found")
    if job.status not in {JobStatus.FAILED, JobStatus.DEAD}:
        raise ApiError(status.HTTP_409_CONFLICT, "job_not_retryable", "Only failed jobs can be retried")
    previous = job.status.value
    job.status = JobStatus.PENDING
    job.next_attempt_at = datetime.now(UTC)
    job.locked_at = None
    job.locked_by = None
    job.last_error_class = None
    job.last_error_message = None
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="outbox.retry",
        object_type="outbox_job",
        object_id=job.id,
        before={"status": previous},
        after={"status": "pending"},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"status": "queued"}


@router.get("/audit-events", response_model=list[dict[str, object]])
async def list_audit_events(_: Viewer, session: DatabaseSession, limit: int = 100) -> list[dict[str, object]]:
    """Return recent append-only audit entries with secret-free metadata."""

    result = await session.execute(
        select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(min(max(limit, 1), 500))
    )
    return [
        {
            "id": event.id,
            "actor_id": event.actor_id,
            "source": event.source,
            "action": event.action,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "before": event.before,
            "after": event.after,
            "metadata": event.metadata_json,
            "correlation_id": event.correlation_id,
            "occurred_at": event.occurred_at,
        }
        for event in result.scalars()
    ]


@router.get("/devices", response_model=list[dict[str, object]])
async def list_devices(_: Viewer, session: DatabaseSession) -> list[dict[str, object]]:
    """List future adapters without ever returning credential hashes."""

    result = await session.execute(select(Device).order_by(Device.device_code))
    return [
        {
            "id": device.id,
            "device_code": device.device_code,
            "device_type": device.device_type,
            "location": device.location,
            "firmware_version": device.firmware_version,
            "enabled": device.enabled,
            "last_seen_at": device.last_seen_at,
        }
        for device in result.scalars()
    ]
