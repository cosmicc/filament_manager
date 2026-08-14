"""PostgreSQL-backed liveness reporting for worker diagnostics."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.operations import WorkerHeartbeat


async def record_worker_heartbeat(
    session: AsyncSession,
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
    """Upsert one bounded heartbeat without exposing job payloads or connection data."""

    now = datetime.now(UTC)
    values = {
        "worker_id": worker_id[:160],
        "worker_type": worker_type[:32],
        "hostname": hostname[:255],
        "status": status[:32],
        "current_job_id": current_job_id,
        "current_job_type": current_job_type[:96] if current_job_type else None,
        "last_error_class": type(error).__name__[:160] if error else None,
        # Exception text can contain connection strings or external response bodies.
        "last_error_message": "Worker operation failed" if error else None,
        "started_at": started_at,
        "last_seen_at": now,
    }
    statement = insert(WorkerHeartbeat).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[WorkerHeartbeat.worker_id],
        set_={key: value for key, value in values.items() if key not in {"worker_id", "started_at"}},
    )
    await session.execute(statement)
    await session.commit()
