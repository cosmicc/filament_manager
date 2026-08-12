"""Physical build-plate inventory, side metadata, maintenance, and selection routes."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.config import get_settings
from filament_manager.domain.build_plates import BuildPlateDiscoveryError, build_plate_sort_key
from filament_manager.models.enums import PlateCondition, PlateStatus
from filament_manager.models.inventory import BuildPlate, BuildPlateSurface, Printer
from filament_manager.services.build_plate_sync import synchronize_build_plates
from filament_manager.services.events import add_audit_event, add_outbox_job

from ..dependencies import Administrator, DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    BuildPlateResponse,
    BuildPlateSurfaceUpdate,
    BuildPlateSyncRequest,
    BuildPlateSyncResponse,
    BuildPlateUpdate,
    PlateSelectRequest,
)

router = APIRouter(prefix="/build-plates", tags=["build plates"])


async def _get_plate(session: DatabaseSession, plate_id: UUID) -> BuildPlate:
    """Load one physical plate and all of its sides without implicit lazy I/O."""

    plate = await session.scalar(
        select(BuildPlate).where(BuildPlate.id == plate_id).options(selectinload(BuildPlate.surfaces))
    )
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    return plate


def _queue_google_plate(session: DatabaseSession, plate: BuildPlate) -> None:
    """Queue the complete physical plate projection after plate or side changes."""

    add_outbox_job(
        session,
        job_type="google.plate.publish",
        idempotency_key=f"plate:{plate.id}:google:v{plate.record_version}",
        aggregate_type="build_plate",
        aggregate_id=plate.id,
        aggregate_version=plate.record_version,
        payload={"plate_id": str(plate.id)},
    )


@router.get("", response_model=list[BuildPlateResponse])
async def list_build_plates(_: Viewer, session: DatabaseSession) -> list[BuildPlateResponse]:
    """Return physical build plates in natural P-number order with nested sides."""

    result = await session.execute(select(BuildPlate).options(selectinload(BuildPlate.surfaces)))
    plates = sorted(result.scalars(), key=lambda plate: build_plate_sort_key(plate.plate_code))
    return [BuildPlateResponse.model_validate(plate) for plate in plates]


@router.post("/synchronize", response_model=BuildPlateSyncResponse)
async def synchronize_with_moonraker(
    payload: BuildPlateSyncRequest,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> BuildPlateSyncResponse:
    """Import exact P-number side meshes and align the active side from Moonraker."""

    printer_code = await session.scalar(select(Printer.printer_code).where(Printer.id == payload.printer_id))
    if printer_code is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found")
    await session.rollback()

    configured_printer = next(
        (item for item in get_settings().moonraker.printers if item.id == printer_code),
        None,
    )
    if configured_printer is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "printer_not_configured",
            "Printer does not have a matching Moonraker configuration",
        )
    try:
        mesh_state = await MoonrakerClient(configured_printer).bed_mesh_state()
        result = await synchronize_build_plates(
            session,
            printer_id=payload.printer_id,
            mesh_state=mesh_state,
            actor_id=administrator.id,
            correlation_id=request.state.correlation_id,
        )
    except MoonrakerError as exc:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "moonraker_mesh_sync_failed",
            "Moonraker build-plate synchronization failed",
        ) from exc
    except BuildPlateDiscoveryError as exc:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "moonraker_mesh_limit_exceeded",
            str(exc),
        ) from exc
    except LookupError as exc:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found") from exc
    return BuildPlateSyncResponse.model_validate(result, from_attributes=True)


@router.get("/{plate_id}", response_model=BuildPlateResponse)
async def get_build_plate(
    plate_id: UUID,
    _: Viewer,
    session: DatabaseSession,
) -> BuildPlateResponse:
    """Return one physical build plate and its sides."""

    return BuildPlateResponse.model_validate(await _get_plate(session, plate_id))


@router.patch("/{plate_id}", response_model=BuildPlateResponse)
async def update_build_plate(
    plate_id: UUID,
    payload: BuildPlateUpdate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> BuildPlateResponse:
    """Update physical plate metadata with optimistic concurrency."""

    plate = await session.scalar(select(BuildPlate).where(BuildPlate.id == plate_id).with_for_update())
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    if plate.record_version != payload.expected_version:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "record_version_conflict",
            "Plate changed; reload and retry",
        )

    before: dict[str, object] = {
        "display_name": plate.display_name,
        "description": plate.description,
        "condition": plate.condition.value,
        "status": plate.status.value,
        "notes": plate.notes,
    }
    if payload.display_name is not None:
        plate.display_name = payload.display_name
    if "description" in payload.model_fields_set:
        plate.description = payload.description
    if payload.condition is not None:
        try:
            plate.condition = PlateCondition(payload.condition)
        except ValueError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_condition",
                "Unknown condition",
            ) from exc
    if payload.status is not None:
        try:
            plate.status = PlateStatus(payload.status)
        except ValueError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_status",
                "Unknown status",
            ) from exc
    if "notes" in payload.model_fields_set:
        plate.notes = payload.notes
    plate.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.update",
        object_type="build_plate",
        object_id=plate.id,
        before=before,
        after={
            "display_name": plate.display_name,
            "description": plate.description,
            "condition": plate.condition.value,
            "status": plate.status.value,
            "notes": plate.notes,
        },
        correlation_id=request.state.correlation_id,
    )
    _queue_google_plate(session, plate)
    await session.commit()
    return BuildPlateResponse.model_validate(await _get_plate(session, plate.id))


@router.patch("/{plate_id}/surfaces/{surface_id}", response_model=BuildPlateResponse)
async def update_build_plate_surface(
    plate_id: UUID,
    surface_id: UUID,
    payload: BuildPlateSurfaceUpdate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> BuildPlateResponse:
    """Update material, texture, and notes for one immutable plate side."""

    plate = await session.scalar(select(BuildPlate).where(BuildPlate.id == plate_id).with_for_update())
    surface = await session.scalar(
        select(BuildPlateSurface)
        .where(
            BuildPlateSurface.id == surface_id,
            BuildPlateSurface.build_plate_id == plate_id,
        )
        .with_for_update()
    )
    if plate is None or surface is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "unknown_build_plate_surface",
            "Build plate side not found",
        )
    if surface.record_version != payload.expected_version:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "record_version_conflict",
            "Plate side changed; reload and retry",
        )
    before: dict[str, object] = {
        "surface_material": surface.surface_material,
        "texture": surface.texture.value if surface.texture else None,
        "notes": surface.notes,
    }
    if "surface_material" in payload.model_fields_set:
        surface.surface_material = payload.surface_material
    if "texture" in payload.model_fields_set:
        surface.texture = payload.texture
    if "notes" in payload.model_fields_set:
        surface.notes = payload.notes
    surface.record_version += 1
    plate.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.surface.update",
        object_type="build_plate_surface",
        object_id=surface.id,
        before=before,
        after={
            "surface_material": surface.surface_material,
            "texture": surface.texture.value if surface.texture else None,
            "notes": surface.notes,
        },
        correlation_id=request.state.correlation_id,
    )
    _queue_google_plate(session, plate)
    await session.commit()
    return BuildPlateResponse.model_validate(await _get_plate(session, plate.id))


@router.post("/{plate_id}/select", status_code=status.HTTP_202_ACCEPTED)
async def select_build_plate(
    plate_id: UUID,
    payload: PlateSelectRequest,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Select one physical plate side and queue its exact same-named mesh load."""

    plate = await session.get(BuildPlate, plate_id)
    surface = await session.get(BuildPlateSurface, payload.surface_id)
    printer = await session.scalar(select(Printer).where(Printer.id == payload.printer_id).with_for_update())
    if plate is None or surface is None or surface.build_plate_id != plate_id:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "unknown_build_plate_surface",
            "Build plate side not found",
        )
    if printer is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found")
    if plate.status != PlateStatus.ACTIVE:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "build_plate_unavailable",
            "Build plate is not active",
        )
    if surface.mesh_available is False:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "plate_mesh_unavailable",
            "The matching Moonraker mesh was not found during the latest synchronization",
        )
    if surface.surface_code != surface.klipper_mesh_profile:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "plate_mesh_unavailable",
            "Plate-side mesh mapping is invalid",
        )

    previous_plate_id = printer.active_plate_id
    previous_surface_id = printer.active_plate_surface_id
    printer.active_plate_id = plate.id
    printer.active_plate_surface_id = surface.id
    printer.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.select",
        object_type="printer",
        object_id=printer.id,
        before={
            "active_plate_id": str(previous_plate_id) if previous_plate_id else None,
            "active_plate_surface_id": str(previous_surface_id) if previous_surface_id else None,
        },
        after={
            "active_plate_id": str(plate.id),
            "active_plate_surface_id": str(surface.id),
            "plate_code": plate.plate_code,
            "surface_code": surface.surface_code,
        },
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="moonraker.build_plate.select",
        idempotency_key=(f"printer:{printer.id}:plate-surface:{surface.id}:v{printer.record_version}"),
        aggregate_type="printer",
        aggregate_id=printer.id,
        aggregate_version=printer.record_version,
        payload={"printer_id": str(printer.id), "plate_code": surface.surface_code},
    )
    await session.commit()
    return {"status": "queued", "surface_code": surface.surface_code}


@router.post("/{plate_id}/maintenance", response_model=BuildPlateResponse)
async def record_maintenance(
    plate_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
    cleaned: bool = False,
    mesh_calibrated: bool = False,
    surface_id: UUID | None = None,
) -> BuildPlateResponse:
    """Record whole-plate cleaning or side-specific mesh calibration."""

    plate = await session.scalar(select(BuildPlate).where(BuildPlate.id == plate_id).with_for_update())
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    if not cleaned and not mesh_calibrated:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "maintenance_empty",
            "Select a maintenance action",
        )
    surface = None
    if mesh_calibrated:
        if surface_id is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "surface_required",
                "Select the plate side whose mesh was calibrated",
            )
        surface = await session.scalar(
            select(BuildPlateSurface)
            .where(
                BuildPlateSurface.id == surface_id,
                BuildPlateSurface.build_plate_id == plate_id,
            )
            .with_for_update()
        )
        if surface is None:
            raise ApiError(
                status.HTTP_404_NOT_FOUND,
                "unknown_build_plate_surface",
                "Build plate side not found",
            )
    now = datetime.now(UTC)
    if cleaned:
        plate.last_cleaned_at = now
    if surface is not None:
        surface.last_mesh_calibrated_at = now
        surface.record_version += 1
    plate.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.maintenance",
        object_type="build_plate",
        object_id=plate.id,
        before=None,
        after={
            "cleaned": cleaned,
            "mesh_calibrated": mesh_calibrated,
            "surface_code": surface.surface_code if surface else None,
        },
        correlation_id=request.state.correlation_id,
    )
    _queue_google_plate(session, plate)
    await session.commit()
    return BuildPlateResponse.model_validate(await _get_plate(session, plate.id))
