"""Dashboard, printers, integrations, audit, outbox, and future-device routes."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from filament_manager.clients.google_sheets import GoogleSheetsClient, GoogleSheetsError
from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.clients.spoolman import SpoolmanClient, SpoolmanError
from filament_manager.config import PrinterConfig, get_settings
from filament_manager.models.auth import User
from filament_manager.models.enums import JobStatus, SpoolStatus
from filament_manager.models.inventory import BuildPlate, FilamentProduct, Printer, Spool
from filament_manager.models.operations import AuditEvent, Device, OutboxJob
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.seed import seed_configured_system

from ..dependencies import Administrator, DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import BuildPlateResponse, DashboardResponse, IntegrationStatus
from .inventory import spool_response

router = APIRouter(tags=["operations"])
SYSTEM_AGGREGATE_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _integration_statuses() -> list[IntegrationStatus]:
    settings = get_settings()
    checked_at = datetime.now(UTC)

    async def spoolman_status() -> IntegrationStatus:
        try:
            await SpoolmanClient(settings.spoolman).health()
            return IntegrationStatus(
                service="Spoolman", status="connected", detail="API healthy", checked_at=checked_at
            )
        except SpoolmanError:
            return IntegrationStatus(
                service="Spoolman", status="unavailable", detail="API check failed", checked_at=checked_at
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
    plate = await session.scalar(
        select(BuildPlate).join(Printer, Printer.active_plate_id == BuildPlate.id).limit(1)
    )
    return DashboardResponse(
        total_spools=total,
        needs_weighing=needs,
        low_spools=low,
        empty_spools=empty,
        active_spool=spool_response(active_spool) if active_spool else None,
        active_plate=BuildPlateResponse.model_validate(plate) if plate else None,
        integrations=await _integration_statuses(),
    )


@router.get("/printers", response_model=list[dict[str, object]])
async def list_printers(_: Viewer, session: DatabaseSession) -> list[dict[str, object]]:
    """List configured canonical printer state."""

    result = await session.execute(select(Printer).order_by(Printer.name))
    return [
        {
            "id": printer.id,
            "printer_code": printer.printer_code,
            "name": printer.name,
            "nozzle_diameter_mm": printer.nozzle_diameter_mm,
            "active_plate_id": printer.active_plate_id,
            "status": printer.status,
            "last_seen_at": printer.last_seen_at,
            "record_version": printer.record_version,
        }
        for printer in result.scalars()
    ]


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
