"""Read-only usage dates from captured identities, never mutable inventory links."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.enums import PrintJobStatus
from filament_manager.models.printing import PrintJob, PrintMaterialSegment

ActivityKind = Literal["filament", "spool", "printer", "nozzle", "plate", "side"]


async def print_activity_dates(
    session: AsyncSession, kind: ActivityKind
) -> dict[UUID, dict[str, datetime | None]]:
    """Aggregate each entity once; material changes include exact segment starts.

    Queued/in-progress and unresolved legacy records do not establish a terminal
    use. A repeated material segment affects the latest date, not print counts.
    """
    attribute = {
        "filament": "filament_product_id",
        "spool": "spool_id",
        "printer": "printer_id",
        "nozzle": "nozzle_id",
        "plate": "build_plate_id",
        "side": "build_plate_surface_id",
    }[kind]
    column = getattr(PrintJob, attribute)
    starts = select(
        column.label("identity"), PrintJob.id.label("job_id"), PrintJob.started_at.label("used_at")
    )
    participants = starts.subquery()
    if kind in {"filament", "spool"}:
        participants = union_all(
            starts,
            select(
                getattr(PrintMaterialSegment, attribute),
                PrintMaterialSegment.print_job_id,
                PrintMaterialSegment.started_at,
            ),
        ).subquery()
    completed = func.max(participants.c.used_at).filter(PrintJob.status == PrintJobStatus.COMPLETED)
    other = func.max(participants.c.used_at).filter(
        PrintJob.status.in_([PrintJobStatus.CANCELLED, PrintJobStatus.FAILED])
    )
    rows = await session.execute(
        select(participants.c.identity, completed, other)
        .join(PrintJob, PrintJob.id == participants.c.job_id)
        .where(
            participants.c.identity.is_not(None),
            participants.c.used_at.is_not(None),
            PrintJob.status.in_([PrintJobStatus.COMPLETED, PrintJobStatus.CANCELLED, PrintJobStatus.FAILED]),
        )
        .group_by(participants.c.identity)
    )
    return {
        identity: {"last_completed_print_at": done, "last_other_print_at": interrupted}
        for identity, done, interrupted in rows
    }
