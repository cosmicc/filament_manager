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


async def worker_loop() -> None:
    """Claim and dispatch jobs until the process receives cancellation."""

    worker_id = f"{socket.gethostname()}-{uuid4()}"
    session_factory = get_session_factory()
    while True:
        async with session_factory() as session:
            scheduled = await schedule_periodic_jobs(session)
            if scheduled:
                logger.info("periodic_jobs_scheduled", count=scheduled)
            jobs = await claim_jobs(session, worker_id)
        if not jobs:
            await asyncio.sleep(1)
            continue
        for claimed in jobs:
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


def run() -> None:
    """Configure logging and start the async worker."""

    configure_logging(get_settings().app.log_level)
    asyncio.run(worker_loop())
