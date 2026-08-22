"""PostgreSQL-coordinated periodic reconciliation scheduling."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.config import get_settings
from filament_manager.models.enums import JobStatus
from filament_manager.models.operations import OutboxJob
from filament_manager.services.events import add_outbox_job

SCHEDULER_LOCK_KEY = 0x464D53594E43
SYSTEM_AGGREGATE_ID = UUID("00000000-0000-0000-0000-000000000001")


async def schedule_periodic_jobs(session: AsyncSession) -> int:
    """Create one idempotent job per configured time bucket across all workers."""

    acquired = await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
        {"lock_key": SCHEDULER_LOCK_KEY},
    )
    if not acquired:
        await session.rollback()
        return 0

    settings = get_settings()
    now = datetime.now(UTC)
    schedules = [
        (
            "spoolman.reconcile.full",
            settings.spoolman.full_reconcile_interval_minutes * 60,
        ),
        (
            "moonraker.state.reconcile",
            settings.sync.moonraker_state_interval_seconds,
        ),
        (
            "moonraker.printer_info.reconcile",
            settings.sync.moonraker_info_interval_seconds,
        ),
        (
            "moonraker.print_history.reconcile",
            settings.sync.moonraker_print_interval_seconds,
        ),
        ("notifications.evaluate", 60),
    ]
    if settings.google.enabled:
        schedules.append(("google.publish.pending", settings.google.publish_interval_seconds))

    created = 0
    for job_type, interval_seconds in schedules:
        active = await session.scalar(
            select(OutboxJob.id).where(
                OutboxJob.job_type == job_type,
                OutboxJob.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
            )
        )
        if active:
            continue
        bucket = int(now.timestamp()) // interval_seconds
        idempotency_key = f"periodic:{job_type}:{bucket}"
        exists = await session.scalar(
            select(OutboxJob.id).where(
                OutboxJob.job_type == job_type,
                OutboxJob.idempotency_key == idempotency_key,
            )
        )
        if exists:
            continue
        # Keep terminal periodic history without allowing one persistent
        # integration fault to become hundreds of actionable dead rows. The
        # replacement remains pending and the newest failure, if any, is still
        # visible in Diagnostics.
        await session.execute(
            update(OutboxJob)
            .where(
                OutboxJob.job_type == job_type,
                OutboxJob.status == JobStatus.DEAD,
                OutboxJob.idempotency_key.like("periodic:%"),
            )
            .values(status=JobStatus.SUPERSEDED, completed_at=now)
        )
        add_outbox_job(
            session,
            job_type=job_type,
            idempotency_key=idempotency_key,
            aggregate_type="system",
            aggregate_id=SYSTEM_AGGREGATE_ID,
            aggregate_version=bucket,
            payload={"scheduled_at": now.isoformat()},
        )
        created += 1
    await session.commit()
    return created
