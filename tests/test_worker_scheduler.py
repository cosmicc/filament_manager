"""Worker scheduling safeguards for frequent complete convergence."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from filament_manager.models.enums import JobStatus
from filament_manager.workers import dispatcher, scheduler


@pytest.mark.asyncio
async def test_scheduler_does_not_queue_overlapping_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow or retrying full sweep must not accumulate one job per minute."""

    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[True, uuid4(), uuid4(), uuid4(), uuid4(), uuid4()]),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            spoolman=SimpleNamespace(full_reconcile_interval_minutes=1),
            sync=SimpleNamespace(
                moonraker_state_interval_seconds=15,
                moonraker_info_interval_seconds=300,
                moonraker_print_interval_seconds=5,
            ),
            google=SimpleNamespace(enabled=False),
        ),
    )

    assert await scheduler.schedule_periodic_jobs(session) == 0  # type: ignore[arg-type]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_realtime_state_retry_never_waits_longer_than_its_poll_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient failure cannot make physical spool state stale for minutes."""

    persisted = SimpleNamespace(
        id=uuid4(),
        job_type="moonraker.state.reconcile",
        status=JobStatus.RUNNING,
        locked_by="worker-1",
        locked_at=datetime.now(UTC),
        attempts=8,
        max_attempts=12,
        last_error_class=None,
        last_error_message=None,
        next_attempt_at=datetime.now(UTC),
    )
    session = SimpleNamespace(get=AsyncMock(return_value=persisted), commit=AsyncMock())
    monkeypatch.setattr(
        dispatcher,
        "get_settings",
        lambda: SimpleNamespace(
            spoolman=SimpleNamespace(full_reconcile_interval_minutes=1),
            sync=SimpleNamespace(
                moonraker_state_interval_seconds=15,
                moonraker_info_interval_seconds=300,
                moonraker_print_interval_seconds=5,
            ),
            google=SimpleNamespace(enabled=False),
        ),
    )
    before = datetime.now(UTC)

    await dispatcher.fail_job(  # type: ignore[arg-type]
        session,
        SimpleNamespace(id=persisted.id, locked_by="worker-1"),
        RuntimeError("temporary failure"),
    )

    assert persisted.status == JobStatus.PENDING
    assert persisted.next_attempt_at <= before.replace(microsecond=0) + dispatcher.timedelta(seconds=16)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_periodic_job_supersedes_older_dead_runs() -> None:
    """Recovered periodic services no longer leave stale dead counts in diagnostics."""

    persisted = SimpleNamespace(
        id=uuid4(),
        job_type="moonraker.state.reconcile",
        idempotency_key="periodic:moonraker.state.reconcile:123",
        status=JobStatus.RUNNING,
        locked_by="worker-1",
        locked_at=datetime.now(UTC),
        completed_at=None,
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=persisted),
        execute=AsyncMock(),
        commit=AsyncMock(),
    )

    await dispatcher.complete_job(  # type: ignore[arg-type]
        session,
        SimpleNamespace(id=persisted.id, locked_by="worker-1"),
    )

    assert persisted.status == JobStatus.COMPLETED
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
