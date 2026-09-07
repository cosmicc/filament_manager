"""Saved products, including archived products, define inventory choice membership."""

from unicodedata import normalize

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.inventory import FilamentAttributeChoice, FilamentColor, FilamentProduct


def choice_key(value: str) -> str:
    """Match names consistently without conflating their display capitalization."""

    return normalize("NFKC", value).strip().casefold()


def normalize_modifier(kind: str, value: str | None) -> str:
    """Use the canonical empty defaults; None is never a finish."""

    name = (value or "").strip()
    if not name or (kind == "finish" and choice_key(name) == "none"):
        return "None" if kind == "filler" else "Standard"
    return name


async def lock_inventory_choices(session: AsyncSession) -> None:
    """Serialize membership writes before product locks so pruning cannot race a save."""

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('inventory-choice-membership', 0))")
    )


async def prune_inventory_choices(session: AsyncSession) -> None:
    """Forget unused catalog metadata, never products or immutable print snapshots.

    Call with the membership lock held and after the complete product mutation.
    The bounded metadata scan also handles Unicode names identically to the picker.
    """

    await session.flush()
    products = (
        await session.execute(
            select(FilamentProduct.color_name, FilamentProduct.filler, FilamentProduct.finish)
        )
    ).all()
    colors = {choice_key(row.color_name) for row in products}
    attributes = {
        kind: {choice_key(normalize_modifier(kind, getattr(row, kind))) for row in products}
        for kind in ("filler", "finish")
    }
    for color in await session.scalars(select(FilamentColor)):
        if color.normalized_name not in colors:
            await session.delete(color)
    for attribute in await session.scalars(select(FilamentAttributeChoice)):
        if choice_key(attribute.name) not in attributes[attribute.kind]:
            await session.delete(attribute)
