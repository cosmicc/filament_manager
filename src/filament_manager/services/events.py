"""Transactional audit and outbox helpers."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.config import get_settings
from filament_manager.models.operations import AuditEvent, OutboxJob

AUDIT_CORRELATION_ID_MAX_LENGTH = 64


def bounded_correlation_id(value: str) -> str:
    """Fit a correlation identifier into storage while retaining collision resistance."""

    if len(value) <= AUDIT_CORRELATION_ID_MAX_LENGTH:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    prefix_length = AUDIT_CORRELATION_ID_MAX_LENGTH - len(digest) - 1
    return f"{value[:prefix_length]}:{digest}"


def add_audit_event(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    source: str,
    action: str,
    object_type: str,
    object_id: UUID | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    correlation_id: str,
    metadata: dict[str, object] | None = None,
) -> AuditEvent:
    """Add an append-only audit event to the active transaction."""

    event = AuditEvent(
        actor_id=actor_id,
        source=source,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
        metadata_json=metadata or {},
        correlation_id=bounded_correlation_id(correlation_id),
        occurred_at=datetime.now(UTC),
    )
    session.add(event)
    return event


def add_outbox_job(
    session: AsyncSession,
    *,
    job_type: str,
    idempotency_key: str,
    aggregate_type: str,
    aggregate_id: UUID,
    aggregate_version: int,
    payload: dict[str, object],
) -> OutboxJob:
    """Add idempotent external work to the active canonical transaction."""

    now = datetime.now(UTC)
    job = OutboxJob(
        job_type=job_type,
        idempotency_key=idempotency_key,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        payload=payload,
        max_attempts=get_settings().sync.max_retry_attempts,
        next_attempt_at=now,
        created_at=now,
    )
    session.add(job)
    return job
