"""Compatibility sink for legacy workstation setting reports.

Filament Manager is the sole authority for managed print settings. Old agents
may still submit reports, but these must never mutate canonical state or create
edit receipts. Keep this boundary explicit during rolling upgrades.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.api.schemas import CuraManagedMaterialReport
from filament_manager.models.workstations import WorkstationAgent


async def import_managed_cura_edits(
    session: AsyncSession,
    *,
    agent: WorkstationAgent,
    reports: list[CuraManagedMaterialReport],
    correlation_id: str,
) -> int:
    """Discard legacy inbound settings; synchronization is strictly outbound."""

    return 0
