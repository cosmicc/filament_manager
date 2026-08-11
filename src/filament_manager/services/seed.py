"""Idempotent first-run seeding for configured workshop resources."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.config import Settings
from filament_manager.models.enums import PlateCondition, PlateStatus
from filament_manager.models.inventory import BuildPlate, Printer


async def seed_configured_system(session: AsyncSession, settings: Settings) -> dict[str, int]:
    """Create missing configured printers and P1-P5 build plates without committing."""

    seeded_plates = 0
    seeded_printers = 0
    for code in settings.plates.allowed_codes:
        if not await session.scalar(select(BuildPlate.id).where(BuildPlate.plate_code == code)):
            session.add(
                BuildPlate(
                    plate_code=code,
                    display_name=f"Build Plate {code}",
                    klipper_mesh_profile=code,
                    condition=PlateCondition.GOOD,
                    status=PlateStatus.ACTIVE,
                )
            )
            seeded_plates += 1
    for configured in settings.moonraker.printers:
        if not await session.scalar(select(Printer.id).where(Printer.printer_code == configured.id)):
            session.add(
                Printer(
                    printer_code=configured.id,
                    name=configured.name,
                    moonraker_base_url=str(configured.base_url),
                    nozzle_diameter_mm=Decimal(str(configured.nozzle_diameter_mm)),
                )
            )
            seeded_printers += 1
    await session.flush()
    return {"plates": seeded_plates, "printers": seeded_printers}
