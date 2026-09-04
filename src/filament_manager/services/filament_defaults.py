"""Currency-safe product costs and canonical-only Spoolman filament defaults."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.enums import ProfileStatus, SpoolStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Spool,
)
from filament_manager.services.events import add_outbox_job


@dataclass(frozen=True)
class ProductCostBasis:
    """An exact weighted cost rate shared by Cura and Spoolman projections."""

    cost_per_gram: Decimal
    currency: str
    source_spool_count: int

    def price_for_weight(self, weight_g: Decimal) -> Decimal:
        """Round only the final total price, never an intermediate kilogram price."""

        return (self.cost_per_gram * weight_g).quantize(Decimal("0.01"))


async def queue_filament_default_projection(
    session: AsyncSession, *, product_id: UUID, source_key: str
) -> None:
    """Queue a dependency change without inventing a product metadata revision."""

    product = await session.get(FilamentProduct, product_id)
    if product is None:
        return
    add_outbox_job(
        session,
        job_type="spoolman.filament.upsert",
        idempotency_key=f"{source_key}:filament:{product.id}:spoolman",
        aggregate_type="filament_product",
        aggregate_id=product.id,
        aggregate_version=product.record_version,
        payload={"filament_id": str(product.id)},
    )


def queue_nozzle_default_projection(session: AsyncSession, *, printer: Printer) -> None:
    """Refresh shared temperatures after a physical nozzle install or removal."""

    add_outbox_job(
        session,
        job_type="spoolman.reconcile.full",
        idempotency_key=f"printer:{printer.id}:nozzle-defaults:v{printer.record_version}",
        aggregate_type="printer",
        aggregate_id=printer.id,
        aggregate_version=printer.record_version,
        payload={},
    )


async def product_cost_bases(
    session: AsyncSession, product_ids: Collection[UUID] | None = None
) -> dict[UUID, ProductCostBasis]:
    """Aggregate usable priced spools once, excluding mixed-currency products."""

    if product_ids is not None and not product_ids:
        return {}
    query = (
        select(
            Spool.filament_product_id,
            func.sum(Spool.purchase_cost).label("total_cost"),
            func.sum(Spool.nominal_net_mass_g).label("total_weight"),
            func.min(Spool.currency).label("currency"),
            func.count().label("spool_count"),
        )
        .where(
            Spool.archived.is_(False),
            Spool.status != SpoolStatus.EMPTY,
            Spool.purchase_cost.is_not(None),
        )
        .group_by(Spool.filament_product_id)
        .having(func.count(func.distinct(Spool.currency)) == 1, func.sum(Spool.nominal_net_mass_g) > 0)
    )
    if product_ids is not None:
        query = query.where(Spool.filament_product_id.in_(product_ids))
    return {
        row.filament_product_id: ProductCostBasis(
            cost_per_gram=row.total_cost / row.total_weight,
            currency=row.currency,
            source_spool_count=row.spool_count,
        )
        for row in await session.execute(query)
    }


def _spoolman_temperature(value: Decimal, maximum: int) -> int | None:
    """Bound and round canonical temperatures to Spoolman's integer contract."""

    if not value.is_finite() or not Decimal("0") <= value <= maximum:
        return None
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


async def spoolman_filament_defaults(
    session: AsyncSession,
    products: Sequence[FilamentProduct],
    *,
    printer_code: str | None,
) -> dict[UUID, dict[str, float | int | None]]:
    """Batch-load exact costs, latest tare, and installed-nozzle temperatures.

    Missing/ambiguous scope and cost evidence explicitly clear remote defaults.
    No printer I/O is needed: nozzle and settings state come from PostgreSQL.
    """

    product_ids = [product.id for product in products]
    if not product_ids:
        return {}
    costs = await product_cost_bases(session, product_ids)
    newest_spools = await session.execute(
        select(Spool.filament_product_id, Spool.tare_mass_g)
        .where(Spool.filament_product_id.in_(product_ids), Spool.archived.is_(False))
        .distinct(Spool.filament_product_id)
        .order_by(Spool.filament_product_id, Spool.created_at.desc(), Spool.id.desc())
    )
    tares = {row.filament_product_id: row.tare_mass_g for row in newest_spools}
    result: dict[UUID, dict[str, float | int | None]] = {
        product.id: {
            "price": float(costs[product.id].price_for_weight(product.nominal_net_mass_g))
            if product.id in costs
            else None,
            "spool_weight": float(tares[product.id]) if product.id in tares else None,
            "settings_extruder_temp": None,
            "settings_bed_temp": None,
        }
        for product in products
    }
    if printer_code is None:
        return result
    profiles = await session.execute(
        select(
            MaterialProfile.filament_product_id,
            MaterialProfile.status,
            MaterialProfile.extruder_temp_c,
            MaterialProfile.bed_temp_c,
            MaterialTemplate.nozzle_id,
            MaterialTemplate.active,
            Printer.active_nozzle_id,
        )
        .join(Printer, Printer.id == MaterialProfile.printer_id)
        .join(
            MaterialTemplateRevision, MaterialTemplateRevision.id == MaterialProfile.base_template_revision_id
        )
        .join(MaterialTemplate, MaterialTemplate.id == MaterialTemplateRevision.material_template_id)
        .where(
            MaterialProfile.filament_product_id.in_(product_ids),
            Printer.printer_code == printer_code,
            MaterialProfile.nozzle_diameter_mm == Printer.nozzle_diameter_mm,
        )
        .distinct(MaterialProfile.filament_product_id)
        .order_by(MaterialProfile.filament_product_id, MaterialProfile.version.desc())
    )
    for (
        product_id,
        profile_status,
        extruder_temp,
        bed_temp,
        template_nozzle_id,
        template_active,
        installed_nozzle_id,
    ) in profiles:
        # Select the latest scope before testing template/status ownership. An
        # older profile must not become current again after rebasing or removal.
        if (
            profile_status != ProfileStatus.PUBLISHED
            or not template_active
            or installed_nozzle_id is None
            or template_nozzle_id != installed_nozzle_id
        ):
            continue
        result[product_id].update(
            settings_extruder_temp=_spoolman_temperature(extruder_temp, 500),
            settings_bed_temp=_spoolman_temperature(bed_temp, 200),
        )
    return result
