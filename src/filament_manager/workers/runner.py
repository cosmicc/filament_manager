"""Long-running outbox worker process."""

import asyncio
import socket
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from filament_manager.config import get_settings
from filament_manager.database import get_session_factory
from filament_manager.logging import configure_logging
from filament_manager.models.enums import JobStatus
from filament_manager.services.database_backups import (
    DatabaseBackupError,
    acquire_backup_lock,
    backup_is_due,
    create_backup_archive,
    prune_automatic_archives,
    record_backup_failure,
    release_backup_lock,
)
from filament_manager.telemetry import ServerTelemetry

from .dispatcher import claim_jobs, complete_job, dispatch_job, fail_job
from .heartbeat import record_worker_heartbeat
from .scheduler import schedule_periodic_jobs

logger = structlog.get_logger()


async def _report_heartbeat(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    worker_id: str,
    worker_type: str,
    hostname: str,
    started_at: datetime,
    status: str,
    current_job_id: UUID | None = None,
    current_job_type: str | None = None,
    error: Exception | None = None,
) -> None:
    """Persist liveness without allowing diagnostics failure to stop useful work."""

    try:
        async with session_factory() as session:
            await record_worker_heartbeat(
                session,
                worker_id=worker_id,
                worker_type=worker_type,
                hostname=hostname,
                started_at=started_at,
                status=status,
                current_job_id=current_job_id,
                current_job_type=current_job_type,
                error=error,
            )
    except Exception as heartbeat_error:
        logger.warning(
            "worker_heartbeat_failed",
            worker_type=worker_type,
            error_class=type(heartbeat_error).__name__,
        )


async def scheduler_loop(telemetry: ServerTelemetry) -> None:
    """Continuously schedule singleton reconciliation and publication work."""

    session_factory = get_session_factory()
    hostname = socket.gethostname()
    worker_id = f"{hostname}-scheduler-{uuid4()}"
    started_at = datetime.now(UTC)
    last_heartbeat = 0.0
    last_backup_check = 0.0
    while True:
        try:
            async with session_factory() as session:
                scheduled = await schedule_periodic_jobs(session)
                if scheduled:
                    logger.info("periodic_jobs_scheduled", count=scheduled)
                if time.monotonic() - last_backup_check >= 60:
                    due, policy = await backup_is_due(session)
                    if due and await acquire_backup_lock(session):
                        try:
                            archive = await asyncio.to_thread(create_backup_archive, "automatic")
                            await asyncio.to_thread(
                                prune_automatic_archives,
                                policy.retention_count,
                            )
                            logger.info(
                                "automatic_database_backup_completed",
                                backup_id=str(archive.id),
                            )
                        except DatabaseBackupError as error:
                            await asyncio.to_thread(record_backup_failure)
                            logger.error(
                                "automatic_database_backup_failed",
                                error_class=type(error).__name__,
                            )
                        finally:
                            await release_backup_lock(session)
                    last_backup_check = time.monotonic()
            if time.monotonic() - last_heartbeat >= 10:
                await _report_heartbeat(
                    session_factory,
                    worker_id=worker_id,
                    worker_type="scheduler",
                    hostname=hostname,
                    started_at=started_at,
                    status="idle",
                )
                last_heartbeat = time.monotonic()
        except Exception as exc:
            telemetry.notify(
                exc,
                context="worker.scheduler",
                metadata={"worker_type": "scheduler"},
                severity="warning",
                throttle_seconds=300,
            )
            await _report_heartbeat(
                session_factory,
                worker_id=worker_id,
                worker_type="scheduler",
                hostname=hostname,
                started_at=started_at,
                status="error",
                error=exc,
            )
            logger.exception(
                "periodic_job_scheduling_failed",
                error_class=type(exc).__name__,
                error=str(exc),
            )
        await asyncio.sleep(1)


async def dispatcher_loop(worker_number: int, telemetry: ServerTelemetry) -> None:
    """Continuously claim and dispatch one job at a time for fair concurrency."""

    hostname = socket.gethostname()
    worker_id = f"{hostname}-dispatcher-{worker_number}-{uuid4()}"
    started_at = datetime.now(UTC)
    last_heartbeat = 0.0
    session_factory = get_session_factory()
    while True:
        try:
            async with session_factory() as session:
                jobs = await claim_jobs(session, worker_id, limit=1)
            if not jobs and time.monotonic() - last_heartbeat >= 10:
                await _report_heartbeat(
                    session_factory,
                    worker_id=worker_id,
                    worker_type="dispatcher",
                    hostname=hostname,
                    started_at=started_at,
                    status="idle",
                )
                last_heartbeat = time.monotonic()
        except Exception as exc:
            telemetry.notify(
                exc,
                context="worker.dispatcher.claim",
                metadata={"worker_number": worker_number, "worker_type": "dispatcher"},
                severity="warning",
                throttle_seconds=300,
            )
            await _report_heartbeat(
                session_factory,
                worker_id=worker_id,
                worker_type="dispatcher",
                hostname=hostname,
                started_at=started_at,
                status="error",
                error=exc,
            )
            logger.exception(
                "outbox_job_claim_failed",
                worker_number=worker_number,
                error_class=type(exc).__name__,
                error=str(exc),
            )
            await asyncio.sleep(1)
            continue
        if not jobs:
            await asyncio.sleep(1)
            continue
        claimed = jobs[0]
        await _report_heartbeat(
            session_factory,
            worker_id=worker_id,
            worker_type="dispatcher",
            hostname=hostname,
            started_at=started_at,
            status="running",
            current_job_id=claimed.id,
            current_job_type=claimed.job_type,
        )
        logger.info(
            "outbox_job_started",
            job_id=str(claimed.id),
            job_type=claimed.job_type,
            attempt=claimed.attempts + 1,
        )
        async with session_factory() as session:
            try:
                await dispatch_job(session, claimed)
                await complete_job(session, claimed)
                await _report_heartbeat(
                    session_factory,
                    worker_id=worker_id,
                    worker_type="dispatcher",
                    hostname=hostname,
                    started_at=started_at,
                    status="idle",
                )
                logger.info("outbox_job_completed", job_id=str(claimed.id), job_type=claimed.job_type)
            except Exception as exc:
                await session.rollback()
                persisted_status = await fail_job(session, claimed, exc)
                if persisted_status == JobStatus.DEAD:
                    telemetry.notify(
                        exc,
                        context=f"worker.outbox.{claimed.job_type}",
                        metadata={
                            "attempt": claimed.attempts + 1,
                            "job_id": str(claimed.id),
                            "job_type": claimed.job_type,
                            "max_attempts": claimed.max_attempts,
                            "terminal": True,
                        },
                        throttle_seconds=300,
                    )
                await _report_heartbeat(
                    session_factory,
                    worker_id=worker_id,
                    worker_type="dispatcher",
                    hostname=hostname,
                    started_at=started_at,
                    status="error",
                    current_job_id=claimed.id,
                    current_job_type=claimed.job_type,
                    error=exc,
                )
                logger.exception(
                    "outbox_job_failed",
                    job_id=str(claimed.id),
                    job_type=claimed.job_type,
                    error_class=type(exc).__name__,
                    error=str(exc),
                )


async def worker_loop(telemetry: ServerTelemetry) -> None:
    """Run the scheduler and configured concurrent outbox dispatchers."""

    worker_count = get_settings().sync.outbox_workers
    await asyncio.gather(
        scheduler_loop(telemetry),
        *(dispatcher_loop(worker_number, telemetry) for worker_number in range(1, worker_count + 1)),
    )


def run() -> None:
    """Configure logging and start the async worker."""

    settings = get_settings()
    configure_logging(settings.app.log_level)
    telemetry = ServerTelemetry(settings.bugsnag, app_type="worker")
    try:
        asyncio.run(worker_loop(telemetry))
    except Exception as exc:
        telemetry.notify(
            exc,
            context="worker.process",
            metadata={"phase": "unhandled_exit"},
            synchronous=True,
        )
        raise
