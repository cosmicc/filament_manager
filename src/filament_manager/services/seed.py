"""Idempotent first-run seeding for configured workshop resources."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.config import Settings
from filament_manager.models.enums import PlateCondition, PlateStatus
from filament_manager.models.inventory import (
    BuildPlate,
    BuildPlateSurface,
    MaterialTemplate,
    Printer,
)
from filament_manager.services.material_settings import save_template_settings

DEFAULT_ASA_SETTINGS: dict[str, object] = {
    "chamber_temp_c": "45",
    "extruder_temp_c": "245",
    "bed_temp_c": "95",
    "flow_percent": "100",
    "print_speed_mm_s": "50",
    "outer_wall_speed_mm_s": None,
    "inner_wall_speed_mm_s": None,
    "infill_speed_mm_s": None,
    "top_bottom_speed_mm_s": None,
    "initial_layer_speed_mm_s": None,
    "travel_speed_mm_s": None,
    "support_speed_mm_s": None,
    "retraction_distance_mm": None,
    "retraction_speed_mm_s": None,
    "cooling_enabled": False,
    "cooling_min_percent": "0",
    "cooling_max_percent": "0",
    "support_overhang_angle_deg": None,
    "tree_max_branch_angle_deg": None,
    "pressure_advance": None,
    "filament_density_g_cm3": "1.07",
    "preferred_build_plate_surface_id": None,
    "cura_extensions": {},
}


async def seed_configured_system(session: AsyncSession, settings: Settings) -> dict[str, int]:
    """Create missing configured printers, plates, and the ASA import base without committing."""

    seeded_plates = 0
    seeded_printers = 0
    seeded_templates = 0
    for code in settings.plates.allowed_codes:
        plate = await session.scalar(select(BuildPlate).where(BuildPlate.plate_code == code))
        if plate is None:
            plate = BuildPlate(
                plate_code=code,
                display_name=f"Build Plate {code}",
                condition=PlateCondition.GOOD,
                status=PlateStatus.ACTIVE,
            )
            session.add(plate)
            await session.flush()
            seeded_plates += 1
        if not await session.scalar(
            select(BuildPlateSurface.id).where(
                BuildPlateSurface.build_plate_id == plate.id,
                BuildPlateSurface.side == "a",
            )
        ):
            session.add(
                BuildPlateSurface(
                    build_plate_id=plate.id,
                    side="a",
                    surface_code=code,
                    klipper_mesh_profile=code,
                )
            )
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
    configured_printer_codes = [configured.id for configured in settings.moonraker.printers]
    configured_printers = list(
        await session.scalars(select(Printer).where(Printer.printer_code.in_(configured_printer_codes)))
    )
    for printer in configured_printers:
        existing_asa = await session.scalar(
            select(MaterialTemplate.id).where(
                func.lower(MaterialTemplate.material_type) == "asa",
                MaterialTemplate.printer_id == printer.id,
                MaterialTemplate.nozzle_diameter_mm == printer.nozzle_diameter_mm,
            )
        )
        if existing_asa is not None:
            continue
        template = MaterialTemplate(
            name="Template ASA",
            material_type="ASA",
            description="Recommended ASA starting point; calibrate or import Cura settings before printing.",
            printer_id=printer.id,
            nozzle_diameter_mm=printer.nozzle_diameter_mm,
            filament_diameter_mm=Decimal("1.75"),
            active=True,
        )
        session.add(template)
        await session.flush()
        await save_template_settings(
            session,
            template=template,
            settings=DEFAULT_ASA_SETTINGS,
            increment_template_record=False,
        )
        seeded_templates += 1
    await session.flush()
    return {
        "plates": seeded_plates,
        "printers": seeded_printers,
        "templates": seeded_templates,
    }
