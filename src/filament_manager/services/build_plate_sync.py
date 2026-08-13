"""Transactional synchronization of physical build plates and sides from Moonraker."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.clients.moonraker import MoonrakerBedMeshState
from filament_manager.domain.build_plates import (
    build_plate_sort_key,
    discover_build_plate_surface_codes,
    is_build_plate_code,
    is_build_plate_surface_code,
    split_build_plate_surface_code,
)
from filament_manager.models.enums import PlateCondition, PlateStatus
from filament_manager.models.inventory import BuildPlate, BuildPlateSurface, Printer
from filament_manager.services.events import add_audit_event, add_outbox_job

BUILD_PLATE_SYNC_LOCK_KEY = 0x464D504C415445


@dataclass(frozen=True, slots=True)
class BuildPlateSyncResult:
    """Sanitized result returned after one successful Moonraker synchronization."""

    printer_id: UUID
    discovered_codes: tuple[str, ...]
    created_codes: tuple[str, ...]
    unavailable_codes: tuple[str, ...]
    ignored_profile_count: int
    active_mesh_profile: str | None
    active_plate_code: str | None
    active_surface_code: str | None
    active_plate_changed: bool
    active_surface_changed: bool
    synchronized_at: datetime


async def synchronize_build_plates(
    session: AsyncSession,
    *,
    printer_id: UUID,
    mesh_state: MoonrakerBedMeshState,
    actor_id: UUID | None,
    correlation_id: str,
) -> BuildPlateSyncResult:
    """Create discovered plate sides and align availability and active side atomically."""

    discovered_codes, ignored_profile_count = discover_build_plate_surface_codes(mesh_state.profile_names)
    discovered_set = set(discovered_codes)
    synchronized_at = datetime.now(UTC)

    # Serialize the canonical mutation without holding a lock during the Moonraker request.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": BUILD_PLATE_SYNC_LOCK_KEY},
    )
    printer = await session.scalar(select(Printer).where(Printer.id == printer_id).with_for_update())
    if printer is None:
        raise LookupError("Printer not found")

    plate_result = await session.execute(select(BuildPlate).with_for_update())
    plates_by_code = {
        plate.plate_code: plate for plate in plate_result.scalars() if is_build_plate_code(plate.plate_code)
    }
    surface_result = await session.execute(select(BuildPlateSurface).with_for_update())
    surfaces_by_code = {
        surface.surface_code: surface
        for surface in surface_result.scalars()
        if is_build_plate_surface_code(surface.surface_code)
    }

    created_codes: list[str] = []
    changed_plate_codes: set[str] = set()
    for surface_code in discovered_codes:
        physical_code, side = split_build_plate_surface_code(surface_code)
        plate = plates_by_code.get(physical_code)
        if plate is None:
            plate = BuildPlate(
                plate_code=physical_code,
                display_name=f"Build Plate {physical_code}",
                condition=PlateCondition.GOOD,
                status=PlateStatus.ACTIVE,
            )
            session.add(plate)
            plates_by_code[physical_code] = plate
            changed_plate_codes.add(physical_code)
            await session.flush()
        if surface_code in surfaces_by_code:
            continue
        surface = BuildPlateSurface(
            build_plate_id=plate.id,
            side=side,
            surface_code=surface_code,
            klipper_mesh_profile=surface_code,
            mesh_available=True,
            last_mesh_checked_at=synchronized_at,
        )
        session.add(surface)
        surfaces_by_code[surface_code] = surface
        created_codes.append(surface_code)
        if physical_code not in changed_plate_codes:
            plate.record_version += 1
            changed_plate_codes.add(physical_code)
    await session.flush()

    unavailable_codes: list[str] = []
    availability_changed = False
    created_set = set(created_codes)
    for code, surface in surfaces_by_code.items():
        available = code in discovered_set and surface.klipper_mesh_profile == code
        if code not in created_set and surface.mesh_available != available:
            surface.mesh_available = available
            surface.record_version += 1
            availability_changed = True
        surface.last_mesh_checked_at = synchronized_at
        if not available:
            unavailable_codes.append(code)

    active_surface = (
        surfaces_by_code.get(mesh_state.active_profile)
        if mesh_state.active_profile in discovered_set
        else None
    )
    active_plate = (
        plates_by_code.get(split_build_plate_surface_code(active_surface.surface_code)[0])
        if active_surface is not None
        else None
    )
    previous_active_plate_id = printer.active_plate_id
    previous_active_surface_id = printer.active_plate_surface_id
    active_plate_changed = active_plate is not None and active_plate.id != previous_active_plate_id
    active_surface_changed = active_surface is not None and active_surface.id != previous_active_surface_id
    if active_plate is not None and active_surface is not None:
        printer.active_plate_id = active_plate.id
        printer.active_plate_surface_id = active_surface.id
    if active_plate_changed or active_surface_changed or printer.status != "connected":
        printer.record_version += 1
    printer.status = "connected"
    printer.last_seen_at = synchronized_at

    for physical_code in changed_plate_codes:
        plate = plates_by_code[physical_code]
        add_outbox_job(
            session,
            job_type="google.plate.publish",
            idempotency_key=f"plate:{plate.id}:google:v{plate.record_version}",
            aggregate_type="build_plate",
            aggregate_id=plate.id,
            aggregate_version=plate.record_version,
            payload={"plate_id": str(plate.id)},
        )

    state_changed = bool(
        created_codes or availability_changed or active_plate_changed or active_surface_changed
    )
    if actor_id is not None or state_changed:
        add_audit_event(
            session,
            actor_id=actor_id,
            source="web" if actor_id is not None else "moonraker",
            action="build_plate.synchronize",
            object_type="printer",
            object_id=printer.id,
            before={
                "active_plate_id": str(previous_active_plate_id) if previous_active_plate_id else None,
                "active_plate_surface_id": (
                    str(previous_active_surface_id) if previous_active_surface_id else None
                ),
            },
            after={
                "active_plate_id": str(printer.active_plate_id) if printer.active_plate_id else None,
                "active_plate_surface_id": (
                    str(printer.active_plate_surface_id) if printer.active_plate_surface_id else None
                ),
                "active_plate_code": active_plate.plate_code if active_plate else None,
                "active_surface_code": active_surface.surface_code if active_surface else None,
                "active_mesh_profile": mesh_state.active_profile,
                "created_surface_codes": created_codes,
                "discovered_surface_count": len(discovered_codes),
                "unavailable_surface_codes": sorted(unavailable_codes, key=build_plate_sort_key),
                "ignored_profile_count": ignored_profile_count,
            },
            correlation_id=correlation_id,
        )
    await session.commit()
    return BuildPlateSyncResult(
        printer_id=printer.id,
        discovered_codes=discovered_codes,
        created_codes=tuple(created_codes),
        unavailable_codes=tuple(sorted(unavailable_codes, key=build_plate_sort_key)),
        ignored_profile_count=ignored_profile_count,
        active_mesh_profile=mesh_state.active_profile,
        active_plate_code=active_plate.plate_code if active_plate else None,
        active_surface_code=active_surface.surface_code if active_surface else None,
        active_plate_changed=active_plate_changed,
        active_surface_changed=active_surface_changed,
        synchronized_at=synchronized_at,
    )
