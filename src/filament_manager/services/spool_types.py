"""Bounded named spool designs used to partition manufacturer tare evidence."""

import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.api.errors import ApiError
from filament_manager.models.inventory import SpoolTypeChoice

DEFAULT_SPOOL_TYPES = (
    "Unknown",
    "Plastic — fixed",
    "Cardboard",
    "Plastic — refillable",
    "Thick plastic",
    "Thin plastic",
)


def spool_type_key(name: str) -> str:
    """Use one Unicode-normalized case-insensitive identity without fuzzy matching."""
    key = unicodedata.normalize("NFKC", name).strip().casefold()
    if len(key) > 320 or any(unicodedata.category(character).startswith("C") for character in key):
        raise ApiError(422, "invalid_spool_type", "Spool type contains unsupported characters or is too long")
    return key


async def resolve_spool_type(session: AsyncSession, name: str | None) -> str:
    """Require explicit choice creation; never silently create from spool form text."""
    key = spool_type_key(name or "")
    for label in DEFAULT_SPOOL_TYPES:
        if key == spool_type_key(label):
            return label
    stored_label = await session.scalar(select(SpoolTypeChoice.name).where(SpoolTypeChoice.name_key == key))
    if stored_label is None:
        raise ApiError(422, "unknown_spool_type", "Select a spool type or use New Spool Type")
    return stored_label
