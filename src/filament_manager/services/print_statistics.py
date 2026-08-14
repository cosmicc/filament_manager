"""Read-only completed-print statistics derived from immutable print history."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.enums import PrintJobStatus
from filament_manager.models.printing import PrintJob, PrintMaterialSegment


async def completed_surface_print_counts(
    session: AsyncSession, surface_ids: list[UUID] | None = None
) -> dict[UUID, int]:
    """Count completed jobs attributed to each exact build-plate side."""

    query = (
        select(PrintJob.build_plate_surface_id, func.count(PrintJob.id))
        .where(
            PrintJob.status == PrintJobStatus.COMPLETED,
            PrintJob.build_plate_surface_id.is_not(None),
        )
        .group_by(PrintJob.build_plate_surface_id)
    )
    if surface_ids is not None:
        if not surface_ids:
            return {}
        query = query.where(PrintJob.build_plate_surface_id.in_(surface_ids))
    rows = await session.execute(query)
    return {surface_id: int(count) for surface_id, count in rows if surface_id is not None}


async def completed_spool_print_counts(
    session: AsyncSession, spool_ids: list[UUID] | None = None
) -> dict[UUID, int]:
    """Count each distinct spool at most once per completed print, including M600 segments."""

    participants = union_all(
        select(PrintJob.id.label("print_job_id"), PrintJob.spool_id.label("spool_id")).where(
            PrintJob.spool_id.is_not(None)
        ),
        select(
            PrintMaterialSegment.print_job_id.label("print_job_id"),
            PrintMaterialSegment.spool_id.label("spool_id"),
        ).where(PrintMaterialSegment.spool_id.is_not(None)),
    ).subquery()
    query = (
        select(participants.c.spool_id, func.count(func.distinct(participants.c.print_job_id)))
        .join(PrintJob, PrintJob.id == participants.c.print_job_id)
        .where(PrintJob.status == PrintJobStatus.COMPLETED)
        .group_by(participants.c.spool_id)
    )
    if spool_ids is not None:
        if not spool_ids:
            return {}
        query = query.where(participants.c.spool_id.in_(spool_ids))
    rows = await session.execute(query)
    return {spool_id: int(count) for spool_id, count in rows if spool_id is not None}


async def completed_nozzle_usage(
    session: AsyncSession, nozzle_ids: list[UUID] | None = None
) -> dict[UUID, tuple[int, Decimal]]:
    """Return completed-print count and recorded filament weight for each physical nozzle."""

    query = (
        select(
            PrintJob.nozzle_id,
            func.count(PrintJob.id),
            func.coalesce(func.sum(PrintJob.actual_filament_weight_g), 0),
        )
        .where(PrintJob.status == PrintJobStatus.COMPLETED, PrintJob.nozzle_id.is_not(None))
        .group_by(PrintJob.nozzle_id)
    )
    if nozzle_ids is not None:
        if not nozzle_ids:
            return {}
        query = query.where(PrintJob.nozzle_id.in_(nozzle_ids))
    rows = await session.execute(query)
    return {
        nozzle_id: (int(count), Decimal(str(weight)))
        for nozzle_id, count, weight in rows
        if nozzle_id is not None
    }
