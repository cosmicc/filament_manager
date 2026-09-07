"""Canonical placeholder manufacturer identity without pooling unrelated brands."""

from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.inventory import Vendor


async def unknown_manufacturer_id(session: AsyncSession) -> UUID:
    """Resolve one Unknown record, serializing with normal manufacturer creation."""

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "manufacturer:unknown"},
    )
    vendor = await session.scalar(select(Vendor).where(func.lower(Vendor.name) == "unknown"))
    if vendor is None:
        vendor = Vendor(name="Unknown")
        session.add(vendor)
        await session.flush()
    return vendor.id
