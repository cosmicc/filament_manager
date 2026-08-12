"""Worker scheduling safeguards for frequent complete convergence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from filament_manager.workers import scheduler


@pytest.mark.asyncio
async def test_scheduler_does_not_queue_overlapping_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow or retrying full sweep must not accumulate one job per minute."""

    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[True, uuid4()]),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            spoolman=SimpleNamespace(full_reconcile_interval_minutes=1),
            google=SimpleNamespace(enabled=False),
        ),
    )

    assert await scheduler.schedule_periodic_jobs(session) == 0  # type: ignore[arg-type]
    session.commit.assert_awaited_once()
