"""Long-running outbox worker process."""

import asyncio
import socket
from uuid import uuid4

import structlog

from filament_manager.config import get_settings
from filament_manager.database import get_session_factory
from filament_manager.logging import configure_logging

from .dispatcher import claim_jobs, complete_job, dispatch_job, fail_job
from .scheduler import schedule_periodic_jobs

logger = structlog.get_logger()


async def scheduler_loop() -> None:
    """Continuously schedule singleton reconciliation and publication work."""

    session_factory = get_session_factory()
    while True:
        async with session_factory() as session:
            scheduled = await schedule_periodic_jobs(session)
            if scheduled:
                logger.info("periodic_jobs_scheduled", count=scheduled)
        await asyncio.sleep(1)


async def dispatcher_loop(worker_number: int) -> None:
    """Continuously claim and dispatch one job at a time for fair concurrency."""

    worker_id = f"{socket.gethostname()}-{worker_number}-{uuid4()}"
    session_factory = get_session_factory()
    while True:
        async with session_factory() as session:
            jobs = await claim_jobs(session, worker_id, limit=1)
        if not jobs:
            await asyncio.sleep(1)
            continue
        claimed = jobs[0]
        async with session_factory() as session:
            try:
                await dispatch_job(session, claimed)
                await complete_job(session, claimed)
                logger.info("outbox_job_completed", job_id=str(claimed.id), job_type=claimed.job_type)
            except Exception as exc:
                await session.rollback()
                await fail_job(session, claimed, exc)
                logger.warning(
                    "outbox_job_failed",
                    job_id=str(claimed.id),
                    job_type=claimed.job_type,
                    error_class=type(exc).__name__,
                )


async def worker_loop() -> None:
    """Run the scheduler and configured concurrent outbox dispatchers."""

    worker_count = get_settings().sync.outbox_workers
    await asyncio.gather(
        scheduler_loop(),
        *(dispatcher_loop(worker_number) for worker_number in range(1, worker_count + 1)),
    )


def run() -> None:
    """Configure logging and start the async worker."""

    configure_logging(get_settings().app.log_level)
    asyncio.run(worker_loop())
