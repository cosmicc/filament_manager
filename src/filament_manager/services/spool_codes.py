"""Allocate immutable human spool identities under a transaction-wide lock."""

import re
import unicodedata
from collections.abc import Iterable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.inventory import Spool


def material_prefix(material_type: str) -> str:
    """Use shared PLA numbering and stable material abbreviations elsewhere."""

    material = unicodedata.normalize("NFKC", material_type).strip().upper()
    known = {"PLA": "P", "PLA+": "P", "PETG": "G", "TPU": "T", "PP": "PP", "SPLA": "S"}
    return known.get(material) or re.sub(r"[^A-Z0-9]", "", material)[:32] or "F"


def next_spool_code(material_type: str, existing_codes: Iterable[str]) -> str:
    """Fill the first positive numeric gap without renaming legacy records."""

    prefix = material_prefix(material_type)
    pattern = re.compile(re.escape(prefix) + r"([0-9]+)", re.IGNORECASE)
    used = {int(match[1]) for code in existing_codes if (match := pattern.fullmatch(code))}
    number = 1
    while number in used:
        number += 1
    return f"{prefix}{number}"


async def allocate_spool_code(session: AsyncSession, material_type: str) -> str:
    """Serialize allocations until commit, including codes retained by archives."""

    await session.execute(text("SELECT pg_advisory_xact_lock(460807082)"))
    codes = await session.scalars(select(Spool.spool_code))
    return next_spool_code(material_type, codes)
