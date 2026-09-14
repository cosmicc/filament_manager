"""Versioned, operator-owned material-template compatibility for exact plate sides."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
)
from filament_manager.models.operations import ApplicationSetting

RATING_PREFIX = "plate_ratings."


async def template_ratings(session: AsyncSession, template_id: UUID) -> dict[str, object]:
    """Read an unrated default without creating persistent settings."""
    setting = await session.scalar(
        select(ApplicationSetting).where(ApplicationSetting.key == f"{RATING_PREFIX}{template_id}")
    )
    return {
        "template_id": str(template_id),
        "record_version": setting.record_version if setting else 0,
        "ratings": setting.value if setting else {},
    }


async def filament_template_id(session: AsyncSession, printer: Printer, filament_id: UUID) -> UUID | None:
    """Resolve the current exact profile before testing active template ownership."""
    profile = await session.scalar(
        select(MaterialProfile)
        .where(
            MaterialProfile.filament_product_id == filament_id,
            MaterialProfile.printer_id == printer.id,
            MaterialProfile.nozzle_diameter_mm == printer.nozzle_diameter_mm,
        )
        .order_by(MaterialProfile.version.desc())
        .limit(1)
    )
    # A product may retain its source template before an exact printer profile
    # exists. Preserve that compatibility only when the scope below matches.
    product = await session.get(FilamentProduct, filament_id) if profile is None else None
    revision_id = (
        profile.base_template_revision_id
        if profile
        else product.source_template_revision_id
        if product
        else None
    )
    revision = await session.get(MaterialTemplateRevision, revision_id) if revision_id else None
    template = await session.get(MaterialTemplate, revision.material_template_id) if revision else None
    return (
        template.id
        if template
        and template.active
        and template.nozzle_id == printer.active_nozzle_id
        and template.printer_id == printer.id
        and template.nozzle_diameter_mm == printer.nozzle_diameter_mm
        else None
    )


async def filament_plate_rating(
    session: AsyncSession, printer: Printer, filament_id: UUID, side_id: UUID | None = None
) -> int | None:
    """Unknown compatibility is distinct from an explicit zero-star prohibition."""
    template_id = await filament_template_id(session, printer, filament_id)
    if template_id is None:
        return None
    payload = await template_ratings(session, template_id)
    ratings = payload["ratings"]
    value = (
        ratings.get(str(side_id or printer.active_plate_surface_id)) if isinstance(ratings, dict) else None
    )
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 5 else None
