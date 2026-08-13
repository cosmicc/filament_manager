"""Build the bounded physical-spool catalog consumed by Klipper macros."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
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
from filament_manager.models.inventory import FilamentProduct, MaterialProfile, Printer, Spool

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


async def latest_published_profile(
    session: AsyncSession, *, spool: Spool, printer: Printer
) -> MaterialProfile | None:
    """Return the current printer/nozzle profile needed for a safe load."""

    profile: MaterialProfile | None = await session.scalar(
        select(MaterialProfile)
        .where(
            MaterialProfile.filament_product_id == spool.filament_product_id,
            MaterialProfile.printer_id == printer.id,
            MaterialProfile.nozzle_diameter_mm == printer.nozzle_diameter_mm,
            MaterialProfile.status == ProfileStatus.PUBLISHED,
        )
        .order_by(MaterialProfile.version.desc())
        .limit(1)
    )
    return profile


async def spool_change_target(session: AsyncSession, *, spool: Spool, printer: Printer) -> SpoolChangeTarget:
    """Resolve one projected spool to its current safe printer profile."""

    if spool.spoolman_id is None or spool.spoolman_id <= 0:
        raise SpoolPreflightError("Project spool to Spoolman before loading it")
    if spool.archived or spool.status not in ELIGIBLE_SPOOL_STATUSES:
        raise SpoolPreflightError("Only an available non-empty spool can be loaded")
    profile = await latest_published_profile(session, spool=spool, printer=printer)
    if profile is None:
        raise SpoolPreflightError(
            "Publish a material profile for the configured printer and nozzle before loading this spool"
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
        temperature_c=profile.extruder_temp_c,
        prompt_label=spool_prompt_label(
            spool.spool_code,
            product.vendor.name if product.vendor else "Filament-Manager",
            product.product_name or product.material_type,
            product.color_name,
        ),
    )


async def build_spool_preflight_catalog(session: AsyncSession, *, printer: Printer) -> SpoolPreflightCatalog:
    """Build exact Cura-material choices for the configured printer/nozzle."""

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
    if not latest_profiles:
        materials: dict[str, list[list[int | str]]] = {}
        temperatures: dict[str, str] = {}
        return SpoolPreflightCatalog(
            materials=materials,
            temperatures=temperatures,
            revision=build_catalog_revision(materials, temperatures),
        )

    spools = list(
        await session.scalars(
            select(Spool)
            .where(
                Spool.filament_product_id.in_(latest_profiles),
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

    materials = {}
    temperatures = {}
    for product_id, profile in latest_profiles.items():
        product_spools = spools_by_product.get(product_id, [])
        if len(product_spools) > MAX_CANDIDATES_PER_MATERIAL:
            raise SpoolPreflightError(
                f"One material contains more than {MAX_CANDIDATES_PER_MATERIAL} eligible spools"
            )
        candidates: list[list[int | str]] = []
        for spool in product_spools:
            if spool.spoolman_id is None:
                continue
            product = spool.filament_product
            label = spool_prompt_label(
                spool.spool_code,
                product.vendor.name if product.vendor else "Filament-Manager",
                product.product_name or product.material_type,
                product.color_name,
            )
            candidates.append([spool.spoolman_id, label])
            temperatures[str(spool.spoolman_id)] = format(profile.extruder_temp_c, "f")
        if candidates:
            materials[cura_material_guid("product", profile.id)] = candidates

    return SpoolPreflightCatalog(
        materials=materials,
        temperatures=temperatures,
        revision=build_catalog_revision(materials, temperatures),
    )
