"""Transactional global material-family identities, independent of print settings."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.api.errors import ApiError
from filament_manager.api.schemas import MaterialTypeCreate
from filament_manager.models.inventory import FilamentProduct, MaterialTemplate, MaterialType, Spool
from filament_manager.models.operations import AuditEvent
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.material_settings import queue_managed_cura_library


async def lock_material_types(session: AsyncSession) -> None:
    """Serialize catalog renames with template/product identity writers."""
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('material-types', 0))"))


async def material_type_was_deleted(session: AsyncSession, name: str) -> bool:
    """Use retained audit tombstones to prevent implicit recreation of removed choices."""
    return (
        await session.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.object_type == "material_type",
                AuditEvent.action == "material_type.delete",
                AuditEvent.before["name_key"].astext == name.casefold(),
            )
            .limit(1)
        )
        is not None
    )


async def remember_material_type(
    session: AsyncSession, name: str, *, explicit_creation: bool = False
) -> MaterialType | None:
    """Retain legacy/API-created labels and reuse case-equivalent identities."""
    name = MaterialTypeCreate(name=name).name
    await lock_material_types(session)
    item = await session.scalar(select(MaterialType).where(MaterialType.name_key == name.casefold()))
    if item is None:
        if not explicit_creation and await material_type_was_deleted(session, name):
            return None
        item = MaterialType(name=name, name_key=name.casefold())
        session.add(item)
        await session.flush()
        add_outbox_job(
            session,
            job_type="google.publish.pending",
            idempotency_key=f"material-type:{item.id}:v{item.record_version}",
            aggregate_type="material_type",
            aggregate_id=item.id,
            aggregate_version=item.record_version,
            payload={},
        )
    return item


async def seeded_material_type_name(session: AsyncSession, original_name: str) -> str | None:
    """Keep recurring seed families attached to their globally renamed catalog identity."""
    # Follow the original catalog UUID, not a chain of mutable text labels.
    # A later operator-created choice with the old name is a separate family.
    events = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.object_type == "material_type", AuditEvent.action == "material_type.rename")
        .order_by(AuditEvent.occurred_at, AuditEvent.id)
    )
    for event in events:
        before = (event.before or {}).get("name")
        if isinstance(before, str) and before.casefold() == original_name.casefold():
            item = await session.get(MaterialType, event.object_id) if event.object_id else None
            if item is not None:
                return item.name
            # A removed renamed seed must not fall back to its former label.
            deleted = await session.scalar(
                select(AuditEvent.id)
                .where(
                    AuditEvent.object_type == "material_type",
                    AuditEvent.action == "material_type.delete",
                    AuditEvent.object_id == event.object_id,
                )
                .limit(1)
            )
            if deleted is not None:
                return None
    existing = await session.scalar(
        select(MaterialType.id).where(MaterialType.name_key == original_name.casefold())
    )
    if existing is None and await material_type_was_deleted(session, original_name):
        return None
    return original_name


async def delete_material_type(
    session: AsyncSession,
    *,
    item: MaterialType,
    actor_id: UUID,
    correlation_id: str,
) -> None:
    """Remove an unused choice, retaining consumers, history, and a recreation tombstone.

    The caller holds the catalog advisory lock, shared by template identity
    writers, so the casefold usage check and deletion form one atomic decision.
    """
    active_names = await session.scalars(
        select(MaterialTemplate.material_type).where(MaterialTemplate.active.is_(True))
    )
    if any(name.casefold() == item.name_key for name in active_names):
        raise ApiError(
            409,
            "material_type_in_use",
            "This material type is used by an active template. Change or delete that template first.",
        )
    add_audit_event(
        session,
        actor_id=actor_id,
        source="web",
        action="material_type.delete",
        object_type="material_type",
        object_id=item.id,
        before={"name": item.name, "name_key": item.name_key, "record_version": item.record_version},
        after=None,
        correlation_id=correlation_id,
    )
    add_outbox_job(
        session,
        job_type="google.publish.pending",
        idempotency_key=f"material-type:{item.id}:delete:v{item.record_version}",
        aggregate_type="material_type",
        aggregate_id=item.id,
        aggregate_version=item.record_version,
        payload={},
    )
    await session.delete(item)


async def rename_material_type(
    session: AsyncSession,
    *,
    item: MaterialType,
    name: str,
    actor_id: UUID | None,
    correlation_id: str,
) -> None:
    """Correct live labels atomically; immutable settings/history and spool IDs stay exact."""
    conflict = await session.scalar(
        select(MaterialType.id).where(MaterialType.name_key == name.casefold(), MaterialType.id != item.id)
    )
    if conflict is not None:
        raise ApiError(409, "material_type_exists", "That material type already exists; choose a unique name")
    old_name = item.name
    templates = list(
        await session.scalars(select(MaterialTemplate).order_by(MaterialTemplate.id).with_for_update())
    )
    affected = [
        template for template in templates if template.material_type.casefold() == old_name.casefold()
    ]
    affected_ids = {template.id for template in affected}
    for template in affected:
        if template.active and any(
            other.id not in affected_ids
            and other.active
            and other.nozzle_id == template.nozzle_id
            and other.material_type.casefold() == name.casefold()
            for other in templates
        ):
            raise ApiError(
                409,
                "material_template_scope_exists",
                "The new name conflicts with an existing nozzle template",
            )
    products = list(
        await session.scalars(select(FilamentProduct).order_by(FilamentProduct.id).with_for_update())
    )
    products = [product for product in products if product.material_type.casefold() == old_name.casefold()]
    for template in affected:
        template.material_type = name
        template.name = f"Template {name}"
        template.record_version += 1
        add_audit_event(
            session,
            actor_id=actor_id,
            source="web",
            action="material_template.material_type.rename",
            object_type="material_template",
            object_id=template.id,
            before={"material_type": old_name},
            after={"material_type": name},
            correlation_id=correlation_id,
        )
    for product in products:
        product.material_type = name
        product.record_version += 1
        add_audit_event(
            session,
            actor_id=actor_id,
            source="web",
            action="filament.material_type.rename",
            object_type="filament_product",
            object_id=product.id,
            before={"material_type": old_name},
            after={"material_type": name},
            correlation_id=correlation_id,
        )
        add_outbox_job(
            session,
            job_type="spoolman.filament.upsert",
            idempotency_key=f"filament:{product.id}:v{product.record_version}",
            aggregate_type="filament_product",
            aggregate_id=product.id,
            aggregate_version=product.record_version,
            payload={"filament_product_id": str(product.id)},
        )
        for spool in await session.scalars(select(Spool).where(Spool.filament_product_id == product.id)):
            add_outbox_job(
                session,
                job_type="spoolman.spool.upsert",
                idempotency_key=f"filament:{product.id}:v{product.record_version}:spool:{spool.id}",
                aggregate_type="spool",
                aggregate_id=spool.id,
                aggregate_version=spool.record_version,
                payload={"spool_id": str(spool.id)},
            )
    item.name = name
    item.name_key = name.casefold()
    item.record_version += 1
    add_audit_event(
        session,
        actor_id=actor_id,
        source="web",
        action="material_type.rename",
        object_type="material_type",
        object_id=item.id,
        before={"name": old_name},
        after={"name": name, "templates_updated": len(affected), "filaments_updated": len(products)},
        correlation_id=correlation_id,
    )
    if affected or products:
        await session.flush()
        await queue_managed_cura_library(session, requested_by=actor_id)
    add_outbox_job(
        session,
        job_type="google.publish.pending",
        idempotency_key=f"material-type:{item.id}:v{item.record_version}",
        aggregate_type="material_type",
        aggregate_id=item.id,
        aggregate_version=item.record_version,
        payload={},
    )
