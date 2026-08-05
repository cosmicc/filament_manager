"""Physical build-plate inventory, maintenance, and selection routes."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from filament_manager.models.enums import PlateCondition, PlateStatus
from filament_manager.models.inventory import BuildPlate, Printer
from filament_manager.services.events import add_audit_event, add_outbox_job

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import BuildPlateResponse, BuildPlateUpdate, PlateSelectRequest

router = APIRouter(prefix="/build-plates", tags=["build plates"])


@router.get("", response_model=list[BuildPlateResponse])
async def list_build_plates(_: Viewer, session: DatabaseSession) -> list[BuildPlateResponse]:
    """Return P1 through P5 in immutable business-code order."""

    result = await session.execute(select(BuildPlate).order_by(BuildPlate.plate_code))
    return [BuildPlateResponse.model_validate(plate) for plate in result.scalars()]


@router.get("/{plate_id}", response_model=BuildPlateResponse)
async def get_build_plate(plate_id: UUID, _: Viewer, session: DatabaseSession) -> BuildPlateResponse:
    """Return one physical build plate."""

    plate = await session.get(BuildPlate, plate_id)
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    return BuildPlateResponse.model_validate(plate)


@router.patch("/{plate_id}", response_model=BuildPlateResponse)
async def update_build_plate(
    plate_id: UUID,
    payload: BuildPlateUpdate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> BuildPlateResponse:
    """Update plate condition and maintenance metadata with a row version."""

    plate = await session.scalar(select(BuildPlate).where(BuildPlate.id == plate_id).with_for_update())
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    if plate.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "record_version_conflict", "Plate changed; reload and retry")

    before: dict[str, object] = {
        "surface_type": plate.surface_type,
        "condition": plate.condition.value,
        "status": plate.status.value,
        "notes": plate.notes,
    }
    if "surface_type" in payload.model_fields_set:
        plate.surface_type = payload.surface_type
    if payload.condition is not None:
        try:
            plate.condition = PlateCondition(payload.condition)
        except ValueError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_condition", "Unknown condition"
            ) from exc
    if payload.status is not None:
        try:
            plate.status = PlateStatus(payload.status)
        except ValueError as exc:
            raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_status", "Unknown status") from exc
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
            "surface_type": plate.surface_type,
            "condition": plate.condition.value,
            "status": plate.status.value,
            "notes": plate.notes,
        },
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="google.plate.publish",
        idempotency_key=f"plate:{plate.id}:google:v{plate.record_version}",
        aggregate_type="build_plate",
        aggregate_id=plate.id,
        aggregate_version=plate.record_version,
        payload={"plate_id": str(plate.id)},
    )
    await session.commit()
    return BuildPlateResponse.model_validate(plate)


@router.post("/{plate_id}/select", status_code=status.HTTP_202_ACCEPTED)
async def select_build_plate(
    plate_id: UUID,
    payload: PlateSelectRequest,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Select a physical plate and queue its matching Klipper mesh load."""

    plate = await session.get(BuildPlate, plate_id)
    printer = await session.scalar(select(Printer).where(Printer.id == payload.printer_id).with_for_update())
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    if printer is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found")
    if plate.status != PlateStatus.ACTIVE:
        raise ApiError(status.HTTP_409_CONFLICT, "build_plate_unavailable", "Build plate is not active")
    if plate.plate_code != plate.klipper_mesh_profile:
        raise ApiError(status.HTTP_409_CONFLICT, "plate_mesh_unavailable", "Plate mesh mapping is invalid")

    previous = printer.active_plate_id
    printer.active_plate_id = plate.id
    printer.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.select",
        object_type="printer",
        object_id=printer.id,
        before={"active_plate_id": str(previous) if previous else None},
        after={"active_plate_id": str(plate.id), "plate_code": plate.plate_code},
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="moonraker.build_plate.select",
        idempotency_key=f"printer:{printer.id}:plate:{plate.id}:v{printer.record_version}",
        aggregate_type="printer",
        aggregate_id=printer.id,
        aggregate_version=printer.record_version,
        payload={"printer_id": str(printer.id), "plate_code": plate.plate_code},
    )
    await session.commit()
    return {"status": "queued", "plate_code": plate.plate_code}


@router.post("/{plate_id}/maintenance", response_model=BuildPlateResponse)
async def record_maintenance(
    plate_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
    cleaned: bool = False,
    mesh_calibrated: bool = False,
) -> BuildPlateResponse:
    """Record cleaning and mesh calibration as separate maintenance facts."""

    plate = await session.scalar(select(BuildPlate).where(BuildPlate.id == plate_id).with_for_update())
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    if not cleaned and not mesh_calibrated:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "maintenance_empty", "Select a maintenance action"
        )
    now = datetime.now(UTC)
    if cleaned:
        plate.last_cleaned_at = now
    if mesh_calibrated:
        plate.last_mesh_calibrated_at = now
    plate.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.maintenance",
        object_type="build_plate",
        object_id=plate.id,
        before=None,
        after={"cleaned": cleaned, "mesh_calibrated": mesh_calibrated},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return BuildPlateResponse.model_validate(plate)
