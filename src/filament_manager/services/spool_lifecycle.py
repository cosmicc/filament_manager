"""Archive exhausted physical inventory without changing loaded-spool authority."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.enums import SpoolStatus
from filament_manager.models.inventory import Spool
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.filament_defaults import queue_filament_default_projection
from filament_manager.services.material_settings import queue_managed_cura_library


async def archive_empty_spool(
    session: AsyncSession,
    spool: Spool,
    *,
    source: str,
    correlation_id: str,
    actor_id: UUID | None = None,
) -> bool:
    """Archive a locked, exhausted spool atomically with audit and projections.

    Loaded spools remain visible until a completed physical unload clears their
    ownership. Positive corrections do not implicitly restore archived inventory;
    an operator may explicitly unarchive it after correcting the remaining mass.
    """

    if spool.archived:
        spool.status = SpoolStatus.ARCHIVED
        return False
    if spool.remaining_mass_effective_g > 0 or spool.active_printer_id is not None:
        return False
    spool.archived = True
    spool.status = SpoolStatus.ARCHIVED
    spool.record_version += 1
    add_audit_event(
        session,
        actor_id=actor_id,
        source=source,
        action="spool.empty.archive",
        object_type="spool",
        object_id=spool.id,
        before={"archived": False},
        after={"archived": True, "remaining_mass_effective_g": "0"},
        correlation_id=correlation_id,
    )
    source_key = f"spool:{spool.id}:empty-archive:v{spool.record_version}"
    for job_type in ("spoolman.spool.upsert", "google.inventory.publish"):
        add_outbox_job(
            session,
            job_type=job_type,
            idempotency_key=f"{source_key}:{job_type}",
            aggregate_type="spool",
            aggregate_id=spool.id,
            aggregate_version=spool.record_version,
            payload={"spool_id": str(spool.id)},
        )
    await queue_filament_default_projection(
        session,
        product_id=spool.filament_product_id,
        source_key=source_key,
    )
    await queue_managed_cura_library(session, requested_by=actor_id)
    return True


async def archive_existing_empty_spools(session: AsyncSession) -> None:
    """Apply the lifecycle rule to existing inventory after usage reconciliation."""

    spools = await session.scalars(
        select(Spool)
        .where(
            Spool.archived.is_(False),
            Spool.remaining_mass_effective_g <= 0,
            Spool.active_printer_id.is_(None),
        )
        .order_by(Spool.id)
        .with_for_update()
    )
    for spool in spools:
        await archive_empty_spool(
            session,
            spool,
            source="worker",
            correlation_id=f"empty-archive-{spool.id}",
        )
