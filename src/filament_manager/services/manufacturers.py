"""Canonical uppercase manufacturer identities and serialized catalog writes."""

from unicodedata import normalize
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.inventory import Vendor


def manufacturer_name(value: str) -> str:
    """Normalize a brand without silently truncating Unicode uppercase expansion."""

    name = normalize("NFKC", value).strip().upper()
    if name.casefold() in {"unspecified", "unspecified manufacturer", "unspecified vendor"}:
        name = "UNKNOWN"
    if not 1 <= len(name) <= 160 or any(not char.isprintable() for char in name):
        raise ValueError("Manufacturer names require 1-160 printable characters after uppercasing")
    return name


async def lock_manufacturers(session: AsyncSession) -> None:
    """Serialize creation, renaming, and placeholder resolution before row locks."""

    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('manufacturer-catalog', 0))"))


async def unknown_manufacturer_id(session: AsyncSession) -> UUID:
    """Resolve the reserved UNKNOWN record without pooling unrelated brands."""

    await lock_manufacturers(session)
    vendor = await session.scalar(select(Vendor).where(Vendor.name == "UNKNOWN"))
    if vendor is None:
        vendor = Vendor(name="UNKNOWN")
        session.add(vendor)
        await session.flush()
    return vendor.id
