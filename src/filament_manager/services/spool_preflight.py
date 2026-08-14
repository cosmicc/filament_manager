"""Build the bounded physical-spool catalog consumed by Klipper macros."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from filament_manager.domain.spool_preflight import (
    MAX_CANDIDATES_PER_MATERIAL,
    MAX_CATALOG_SPOOLS,
    SpoolPreflightCatalog,
    SpoolPreflightError,
    build_catalog_revision,
    cura_material_guid,
    spool_prompt_label,
)
from filament_manager.models.enums import ProfileStatus, SpoolStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Spool,
)

ELIGIBLE_SPOOL_STATUSES = (
    SpoolStatus.NEEDS_WEIGHING,
    SpoolStatus.IN_STOCK,
    SpoolStatus.LOW,
)


@dataclass(frozen=True, slots=True)
class SpoolChangeTarget:
    """Validated physical-spool values passed to the printer."""

    spoolman_id: int
    temperature_c: Decimal
    prompt_label: str


async def latest_load_profile(
    session: AsyncSession, *, spool: Spool, printer: Printer
) -> MaterialProfile | None:
    """Return the newest non-archived exact profile for physical loading."""

    profile: MaterialProfile | None = await session.scalar(
        select(MaterialProfile)
        .where(
            MaterialProfile.filament_product_id == spool.filament_product_id,
            MaterialProfile.printer_id == printer.id,
            MaterialProfile.nozzle_diameter_mm == printer.nozzle_diameter_mm,
            MaterialProfile.status != ProfileStatus.ARCHIVED,
        )
        .order_by(MaterialProfile.version.desc())
        .limit(1)
    )
    return profile


async def manual_load_temperature(session: AsyncSession, *, spool: Spool, printer: Printer) -> Decimal | None:
    """Resolve a safe load temperature without weakening Cura print preflight."""

    profile = await latest_load_profile(session, spool=spool, printer=printer)
    if profile is not None:
        return _bounded_temperature(profile.extruder_temp_c)

    product = await session.get(FilamentProduct, spool.filament_product_id)
    if product is None or product.source_template_revision_id is None:
        return None
    template_revision = await session.scalar(
        select(MaterialTemplateRevision)
        .join(
            MaterialTemplate,
            MaterialTemplate.id == MaterialTemplateRevision.material_template_id,
        )
        .where(
            MaterialTemplateRevision.id == product.source_template_revision_id,
            MaterialTemplate.printer_id == printer.id,
            MaterialTemplate.nozzle_diameter_mm == printer.nozzle_diameter_mm,
            MaterialTemplateRevision.status != ProfileStatus.ARCHIVED,
        )
    )
    if template_revision is None:
        return None
    return _bounded_temperature(template_revision.settings.get("extruder_temp_c"))


def _bounded_temperature(value: object) -> Decimal | None:
    """Convert one stored temperature and enforce the printer-side safety bound."""

    try:
        temperature = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return temperature if Decimal("0") < temperature <= Decimal("500") else None


async def spool_change_target(session: AsyncSession, *, spool: Spool, printer: Printer) -> SpoolChangeTarget:
    """Resolve one projected spool to its current safe printer profile."""

    if spool.spoolman_id is None or spool.spoolman_id <= 0:
        raise SpoolPreflightError("Project spool to Spoolman before loading it")
    if spool.archived or spool.status not in ELIGIBLE_SPOOL_STATUSES:
        raise SpoolPreflightError("Only an available non-empty spool can be loaded")
    temperature = await manual_load_temperature(session, spool=spool, printer=printer)
    if temperature is None:
        raise SpoolPreflightError(
            "Create an exact material profile or linked template for the configured printer and nozzle "
            "before loading this spool"
        )
    product = await session.scalar(
        select(FilamentProduct)
        .where(FilamentProduct.id == spool.filament_product_id)
        .options(joinedload(FilamentProduct.vendor))
    )
    if product is None:
        raise SpoolPreflightError("Spool references a missing filament product")
    return SpoolChangeTarget(
        spoolman_id=spool.spoolman_id,
        temperature_c=temperature,
        prompt_label=spool_prompt_label(
            spool.spool_code,
            product.vendor.name if product.vendor else "Filament-Manager",
            product.product_name or product.material_type,
            product.color_name,
        ),
    )


async def build_spool_preflight_catalog(session: AsyncSession, *, printer: Printer) -> SpoolPreflightCatalog:
    """Build strict Cura choices plus the broader safe manual-load catalog."""

    profiles = list(
        await session.scalars(
            select(MaterialProfile)
            .where(
                MaterialProfile.printer_id == printer.id,
                MaterialProfile.nozzle_diameter_mm == printer.nozzle_diameter_mm,
                MaterialProfile.status == ProfileStatus.PUBLISHED,
            )
            .order_by(
                MaterialProfile.filament_product_id,
                MaterialProfile.version.desc(),
                MaterialProfile.id,
            )
        )
    )
    latest_profiles: dict[UUID, MaterialProfile] = {}
    for profile in profiles:
        latest_profiles.setdefault(profile.filament_product_id, profile)
    spools = list(
        await session.scalars(
            select(Spool)
            .where(
                Spool.spoolman_id.is_not(None),
                Spool.archived.is_(False),
                Spool.status.in_(ELIGIBLE_SPOOL_STATUSES),
                Spool.remaining_mass_effective_g > 0,
            )
            .options(joinedload(Spool.filament_product).joinedload(FilamentProduct.vendor))
            .order_by(Spool.spool_code, Spool.id)
        )
    )
    if len(spools) > MAX_CATALOG_SPOOLS:
        raise SpoolPreflightError(f"Printer catalog contains more than {MAX_CATALOG_SPOOLS} eligible spools")

    spools_by_product: dict[UUID, list[Spool]] = defaultdict(list)
    for spool in spools:
        spools_by_product[spool.filament_product_id].append(spool)

    product_ids = set(spools_by_product)
    load_profiles = list(
        await session.scalars(
            select(MaterialProfile)
            .where(
                MaterialProfile.filament_product_id.in_(product_ids),
                MaterialProfile.printer_id == printer.id,
                MaterialProfile.nozzle_diameter_mm == printer.nozzle_diameter_mm,
                MaterialProfile.status != ProfileStatus.ARCHIVED,
            )
            .order_by(
                MaterialProfile.filament_product_id,
                MaterialProfile.version.desc(),
                MaterialProfile.id,
            )
        )
    )
    latest_load_profiles: dict[UUID, MaterialProfile] = {}
    for load_profile in load_profiles:
        latest_load_profiles.setdefault(load_profile.filament_product_id, load_profile)

    source_template_ids = {
        spool.filament_product.source_template_revision_id
        for spool in spools
        if spool.filament_product_id not in latest_load_profiles
        and spool.filament_product.source_template_revision_id is not None
    }
    template_revisions: dict[UUID, MaterialTemplateRevision] = {}
    if source_template_ids:
        matching_template_revisions = list(
            await session.scalars(
                select(MaterialTemplateRevision)
                .join(
                    MaterialTemplate,
                    MaterialTemplate.id == MaterialTemplateRevision.material_template_id,
                )
                .where(
                    MaterialTemplateRevision.id.in_(source_template_ids),
                    MaterialTemplate.printer_id == printer.id,
                    MaterialTemplate.nozzle_diameter_mm == printer.nozzle_diameter_mm,
                    MaterialTemplateRevision.status != ProfileStatus.ARCHIVED,
                )
            )
        )
        template_revisions = {revision.id: revision for revision in matching_template_revisions}

    materials: dict[str, list[list[int | str]]] = {}
    manual_spools: list[list[int | str]] = []
    print_temperatures: dict[str, str] = {}
    temperatures: dict[str, str] = {}
    manual_temperatures: dict[UUID, Decimal] = {}
    for spool in spools:
        resolved_profile = latest_load_profiles.get(spool.filament_product_id)
        source_template_id = spool.filament_product.source_template_revision_id
        template_revision = template_revisions.get(source_template_id) if source_template_id else None
        temperature = _bounded_temperature(
            resolved_profile.extruder_temp_c
            if resolved_profile is not None
            else template_revision.settings.get("extruder_temp_c")
            if template_revision is not None
            else None
        )
        if temperature is None or spool.spoolman_id is None:
            continue
        manual_temperatures[spool.id] = temperature
        product = spool.filament_product
        manual_spools.append(
            [
                spool.spoolman_id,
                spool_prompt_label(
                    spool.spool_code,
                    product.vendor.name if product.vendor else "Filament-Manager",
                    product.product_name or product.material_type,
                    product.color_name,
                ),
            ]
        )
        temperatures[str(spool.spoolman_id)] = format(temperature, "f")

    for product_id, profile in latest_profiles.items():
        product_spools = spools_by_product.get(product_id, [])
        if len(product_spools) > MAX_CANDIDATES_PER_MATERIAL:
            raise SpoolPreflightError(
                f"One material contains more than {MAX_CANDIDATES_PER_MATERIAL} eligible spools"
            )
        candidates: list[list[int | str]] = []
        for spool in product_spools:
            if spool.spoolman_id is None or spool.id not in manual_temperatures:
                continue
            product = spool.filament_product
            label = spool_prompt_label(
                spool.spool_code,
                product.vendor.name if product.vendor else "Filament-Manager",
                product.product_name or product.material_type,
                product.color_name,
            )
            candidates.append([spool.spoolman_id, label])
            print_temperatures[str(spool.spoolman_id)] = format(profile.extruder_temp_c, "f")
        if candidates:
            materials[cura_material_guid("product", profile.id)] = candidates

    return SpoolPreflightCatalog(
        materials=materials,
        manual_spools=manual_spools,
        print_temperatures=print_temperatures,
        temperatures=temperatures,
        revision=build_catalog_revision(
            materials,
            manual_spools,
            print_temperatures,
            temperatures,
        ),
    )
