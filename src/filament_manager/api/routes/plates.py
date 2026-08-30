"""Physical build-plate inventory, side metadata, maintenance, and selection routes."""

import hashlib
import warnings
from datetime import UTC, datetime
from io import BytesIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Request, Response, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.config import get_settings
from filament_manager.domain.build_plates import BuildPlateDiscoveryError, build_plate_sort_key
from filament_manager.models.enums import PlateCondition, PlateMaintenanceType, PlateStatus
from filament_manager.models.inventory import BuildPlate, BuildPlateSurface, Printer
from filament_manager.models.operations import BuildPlateMaintenanceEvent
from filament_manager.services.build_plate_sync import BUILD_PLATE_SYNC_LOCK_KEY, synchronize_build_plates
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.notifications import build_plate_maintenance_status
from filament_manager.services.print_statistics import completed_surface_print_counts

from ..dependencies import Administrator, DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    BuildPlateMaintenanceCreate,
    BuildPlateMaintenanceEventResponse,
    BuildPlateMaintenanceStatus,
    BuildPlateResponse,
    BuildPlateSurfaceCreate,
    BuildPlateSurfaceResponse,
    BuildPlateSurfaceUpdate,
    BuildPlateSyncRequest,
    BuildPlateSyncResponse,
    BuildPlateUpdate,
    PlateSelectRequest,
)

router = APIRouter(prefix="/build-plates", tags=["build plates"])
MAX_PLATE_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PLATE_IMAGE_PIXELS = 16_000_000
MAX_PLATE_IMAGE_SIDE = 1024


async def _get_plate(session: DatabaseSession, plate_id: UUID) -> BuildPlate:
    """Load one physical plate and all of its sides without implicit lazy I/O."""

    plate = await session.scalar(
        select(BuildPlate)
        .where(BuildPlate.id == plate_id)
        .options(selectinload(BuildPlate.surfaces))
        .execution_options(populate_existing=True)
    )
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    return plate


async def build_plate_response(
    session: DatabaseSession,
    plate: BuildPlate,
    print_counts: dict[UUID, int] | None = None,
) -> BuildPlateResponse:
    """Render one physical plate with completed-print totals for each exact side."""

    counts = print_counts
    if counts is None:
        counts = await completed_surface_print_counts(session, [surface.id for surface in plate.surfaces])
    response = BuildPlateResponse.model_validate(plate)
    return response.model_copy(
        update={
            "image_url": (
                f"/api/v1/build-plates/{plate.id}/image?v={plate.image_version}"
                if plate.image_data is not None
                else None
            ),
            "surfaces": [
                BuildPlateSurfaceResponse.model_validate(surface).model_copy(
                    update={"completed_print_count": counts.get(surface.id, 0)}
                )
                for surface in plate.surfaces
            ],
        }
    )


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
    counts = await completed_surface_print_counts(
        session, [surface.id for plate in plates for surface in plate.surfaces]
    )
    return [await build_plate_response(session, plate, counts) for plate in plates]


@router.post("", response_model=BuildPlateResponse, status_code=status.HTTP_201_CREATED)
async def create_build_plate(
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> BuildPlateResponse:
    """Create the next physical P-number plate with an unavailable Side A mesh."""

    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": BUILD_PLATE_SYNC_LOCK_KEY},
    )
    existing_codes = list(await session.scalars(select(BuildPlate.plate_code).with_for_update()))
    existing_numbers = [
        int(code[1:])
        for code in existing_codes
        if code.startswith("P") and code[1:].isdigit() and int(code[1:]) > 0
    ]
    plate_code = f"P{max(existing_numbers, default=0) + 1}"
    plate = BuildPlate(
        plate_code=plate_code,
        display_name=f"Build Plate {plate_code}",
        condition=PlateCondition.GOOD,
        status=PlateStatus.ACTIVE,
    )
    session.add(plate)
    await session.flush()
    surface = BuildPlateSurface(
        build_plate_id=plate.id,
        side="a",
        surface_code=plate_code,
        klipper_mesh_profile=plate_code,
        mesh_available=False,
    )
    session.add(surface)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.create",
        object_type="build_plate",
        object_id=plate.id,
        before=None,
        after={
            "plate_code": plate_code,
            "surface_code": plate_code,
            "mesh_available": False,
        },
        correlation_id=request.state.correlation_id,
    )
    _queue_google_plate(session, plate)
    await session.commit()
    return await build_plate_response(session, await _get_plate(session, plate.id))


@router.get("/maintenance/status", response_model=list[BuildPlateMaintenanceStatus])
async def list_maintenance_status(_: Viewer, session: DatabaseSession) -> list[BuildPlateMaintenanceStatus]:
    """Return day/print due state for every plate and side."""

    plates = list(await session.scalars(select(BuildPlate).order_by(BuildPlate.plate_code)))
    return [
        BuildPlateMaintenanceStatus.model_validate(await build_plate_maintenance_status(session, plate))
        for plate in plates
    ]


@router.get("/maintenance/events", response_model=list[BuildPlateMaintenanceEventResponse])
async def list_maintenance_events(
    _: Viewer,
    session: DatabaseSession,
    plate_id: UUID | None = None,
    maintenance_type: PlateMaintenanceType | None = None,
    limit: int = 100,
) -> list[BuildPlateMaintenanceEventResponse]:
    """Return filterable immutable plate-maintenance history."""

    query = select(BuildPlateMaintenanceEvent).order_by(BuildPlateMaintenanceEvent.occurred_at.desc())
    if plate_id is not None:
        query = query.where(BuildPlateMaintenanceEvent.build_plate_id == plate_id)
    if maintenance_type is not None:
        query = query.where(BuildPlateMaintenanceEvent.maintenance_type == maintenance_type)
    events = await session.scalars(query.limit(min(max(limit, 1), 500)))
    return [BuildPlateMaintenanceEventResponse.model_validate(event) for event in events]


@router.post("/active/clear", status_code=status.HTTP_202_ACCEPTED)
async def clear_active_build_plate(
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Queue mesh clearing; reconciliation clears canonical context after confirmation."""

    configured_code = get_settings().moonraker.printers[0].id
    printer = await session.scalar(select(Printer).where(Printer.printer_code == configured_code))
    if printer is None or printer.active_plate_surface_id is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "no_active_build_plate",
            "No build plate side is selected for the configured printer",
        )
    add_outbox_job(
        session,
        job_type="moonraker.build_plate.clear",
        idempotency_key=f"build-plate-clear:{printer.id}:{request.state.correlation_id}",
        aggregate_type="printer",
        aggregate_id=printer.id,
        aggregate_version=printer.record_version,
        payload={"printer_id": str(printer.id)},
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.clear.request",
        object_type="printer",
        object_id=printer.id,
        before={
            "active_plate_id": str(printer.active_plate_id) if printer.active_plate_id else None,
            "active_plate_surface_id": str(printer.active_plate_surface_id),
        },
        after={"mesh_clear_queued": True},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"status": "clear_queued", "printer_name": printer.name}


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

    return await build_plate_response(session, await _get_plate(session, plate_id))


def _sanitize_plate_image(payload: bytes) -> bytes:
    """Decode, bound, orient, and re-encode an untrusted plate image as WebP."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as source:
                if source.width * source.height > MAX_PLATE_IMAGE_PIXELS:
                    raise ValueError("Build plate image dimensions are too large")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError) as exc:
        raise ValueError("Upload a valid PNG, JPEG, or WebP image") from exc
    image.thumbnail((MAX_PLATE_IMAGE_SIDE, MAX_PLATE_IMAGE_SIDE), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="WEBP", quality=86, method=6)
    return output.getvalue()


@router.get("/{plate_id}/image")
async def get_build_plate_image(
    plate_id: UUID,
    _: Viewer,
    session: DatabaseSession,
) -> Response:
    """Return an authenticated sanitized image without exposing database metadata."""

    plate = await session.get(BuildPlate, plate_id)
    if plate is None or plate.image_data is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "build_plate_image_missing", "Build plate image not found")
    return Response(
        content=plate.image_data,
        media_type=plate.image_media_type or "image/webp",
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": f'"{plate.image_sha256}"',
        },
    )


@router.put("/{plate_id}/image", response_model=BuildPlateResponse)
async def upload_build_plate_image(
    plate_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
    image: Annotated[UploadFile, File()],
) -> BuildPlateResponse:
    """Replace a plate image with one bounded server-sanitized WebP file."""

    plate = await session.scalar(select(BuildPlate).where(BuildPlate.id == plate_id).with_for_update())
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    payload = await image.read(MAX_PLATE_IMAGE_UPLOAD_BYTES + 1)
    if not payload or len(payload) > MAX_PLATE_IMAGE_UPLOAD_BYTES:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "build_plate_image_size",
            "Build plate images must be between 1 byte and 5 MB",
        )
    try:
        sanitized = _sanitize_plate_image(payload)
    except ValueError as exc:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "build_plate_image_invalid", str(exc)) from exc
    before_sha = plate.image_sha256
    plate.image_data = sanitized
    plate.image_media_type = "image/webp"
    plate.image_sha256 = hashlib.sha256(sanitized).hexdigest()
    plate.image_version += 1
    plate.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.image.update",
        object_type="build_plate",
        object_id=plate.id,
        before={"image_sha256": before_sha},
        after={"image_sha256": plate.image_sha256, "media_type": plate.image_media_type},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return await build_plate_response(session, await _get_plate(session, plate.id))


@router.delete("/{plate_id}/image", response_model=BuildPlateResponse)
async def delete_build_plate_image(
    plate_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> BuildPlateResponse:
    """Remove a plate image while retaining the canonical physical plate."""

    plate = await session.scalar(select(BuildPlate).where(BuildPlate.id == plate_id).with_for_update())
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    before_sha = plate.image_sha256
    plate.image_data = None
    plate.image_media_type = None
    plate.image_sha256 = None
    plate.image_version += 1
    plate.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.image.delete",
        object_type="build_plate",
        object_id=plate.id,
        before={"image_sha256": before_sha},
        after={"image_sha256": None},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return await build_plate_response(session, await _get_plate(session, plate.id))


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
        "manufacturer": plate.manufacturer,
        "product_name": plate.product_name,
        "shape": plate.shape,
        "dimensions_mm": plate.dimensions_mm,
        "magnetic": plate.magnetic,
        "flexible": plate.flexible,
        "condition": plate.condition.value,
        "status": plate.status.value,
        "preferred_materials": plate.preferred_materials,
        "max_bed_temp_c": str(plate.max_bed_temp_c) if plate.max_bed_temp_c is not None else None,
        "notes": plate.notes,
    }
    if payload.display_name is not None:
        plate.display_name = payload.display_name
    if "description" in payload.model_fields_set:
        plate.description = payload.description
    for field in ("manufacturer", "product_name", "shape"):
        if field in payload.model_fields_set:
            value = getattr(payload, field)
            setattr(plate, field, value.strip() or None if isinstance(value, str) else value)
    if "dimensions_mm" in payload.model_fields_set:
        plate.dimensions_mm = (
            payload.dimensions_mm.model_dump(mode="json", exclude_none=True)
            if payload.dimensions_mm is not None
            else {}
        )
    if "magnetic" in payload.model_fields_set:
        plate.magnetic = payload.magnetic
    if "flexible" in payload.model_fields_set:
        plate.flexible = payload.flexible
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
    if payload.preferred_materials is not None:
        normalized_materials = [item.strip() for item in payload.preferred_materials if item.strip()]
        if any(len(item) > 48 for item in normalized_materials):
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_preferred_material",
                "Preferred material names must not exceed 48 characters",
            )
        plate.preferred_materials = list(dict.fromkeys(normalized_materials))
    if "max_bed_temp_c" in payload.model_fields_set:
        plate.max_bed_temp_c = payload.max_bed_temp_c
    for field in (
        "cleaning_due_after_prints",
        "cleaning_due_after_days",
        "mesh_due_after_prints",
        "mesh_due_after_days",
    ):
        if field in payload.model_fields_set:
            value = getattr(payload, field)
            if value is not None:
                setattr(plate, field, value)
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
            "manufacturer": plate.manufacturer,
            "product_name": plate.product_name,
            "shape": plate.shape,
            "dimensions_mm": plate.dimensions_mm,
            "magnetic": plate.magnetic,
            "flexible": plate.flexible,
            "condition": plate.condition.value,
            "status": plate.status.value,
            "preferred_materials": plate.preferred_materials,
            "max_bed_temp_c": (str(plate.max_bed_temp_c) if plate.max_bed_temp_c is not None else None),
            "notes": plate.notes,
        },
        correlation_id=request.state.correlation_id,
    )
    _queue_google_plate(session, plate)
    await session.commit()
    return await build_plate_response(session, await _get_plate(session, plate.id))


@router.post(
    "/{plate_id}/surfaces",
    response_model=BuildPlateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_build_plate_side_b(
    plate_id: UUID,
    payload: BuildPlateSurfaceCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> BuildPlateResponse:
    """Add the physical Side B while Moonraker remains authoritative for mesh availability."""

    plate = await session.scalar(
        select(BuildPlate)
        .where(BuildPlate.id == plate_id)
        .options(selectinload(BuildPlate.surfaces))
        .with_for_update()
    )
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    if any(surface.side == "b" for surface in plate.surfaces):
        raise ApiError(status.HTTP_409_CONFLICT, "side_b_exists", "Side B already exists")
    surface_code = f"{plate.plate_code}b"
    surface = BuildPlateSurface(
        build_plate_id=plate.id,
        side="b",
        surface_code=surface_code,
        klipper_mesh_profile=surface_code,
        surface_material=payload.surface_material.strip() if payload.surface_material else None,
        texture=payload.texture,
        mesh_available=False,
        notes=payload.notes.strip() if payload.notes else None,
    )
    session.add(surface)
    plate.record_version += 1
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.side_b.create",
        object_type="build_plate_surface",
        object_id=surface.id,
        before=None,
        after={
            "plate_code": plate.plate_code,
            "surface_code": surface.surface_code,
            "mesh_available": False,
        },
        correlation_id=request.state.correlation_id,
    )
    _queue_google_plate(session, plate)
    await session.commit()
    return await build_plate_response(session, await _get_plate(session, plate.id))


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
    return await build_plate_response(session, await _get_plate(session, plate.id))


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


@router.post(
    "/{plate_id}/maintenance-events",
    response_model=BuildPlateMaintenanceEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_maintenance_event(
    plate_id: UUID,
    payload: BuildPlateMaintenanceCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> BuildPlateMaintenanceEventResponse:
    """Append one cleaning or side-specific mesh-calibration event."""

    plate = await session.scalar(select(BuildPlate).where(BuildPlate.id == plate_id).with_for_update())
    if plate is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_build_plate", "Build plate not found")
    surface = None
    if payload.maintenance_type == PlateMaintenanceType.MESH_CALIBRATED:
        if payload.surface_id is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "surface_required",
                "Select the plate side whose mesh was calibrated",
            )
        surface = await session.scalar(
            select(BuildPlateSurface)
            .where(
                BuildPlateSurface.id == payload.surface_id,
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
    elif payload.surface_id is not None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "surface_not_allowed",
            "Cleaning applies to the whole physical plate",
        )
    now = datetime.now(UTC)
    event = BuildPlateMaintenanceEvent(
        build_plate_id=plate.id,
        build_plate_surface_id=surface.id if surface else None,
        maintenance_type=payload.maintenance_type,
        performed_by=operator.id,
        source="web",
        notes=payload.notes.strip() if payload.notes else None,
        occurred_at=now,
        created_at=now,
    )
    session.add(event)
    if payload.maintenance_type == PlateMaintenanceType.CLEANED:
        plate.last_cleaned_at = now
    if surface is not None:
        surface.last_mesh_calibrated_at = now
        surface.record_version += 1
    plate.record_version += 1
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="build_plate.maintenance",
        object_type="build_plate_maintenance_event",
        object_id=event.id,
        before=None,
        after={
            "build_plate_id": str(plate.id),
            "maintenance_type": event.maintenance_type.value,
            "surface_code": surface.surface_code if surface else None,
        },
        correlation_id=request.state.correlation_id,
    )
    _queue_google_plate(session, plate)
    await session.commit()
    return BuildPlateMaintenanceEventResponse.model_validate(event)


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
        session.add(
            BuildPlateMaintenanceEvent(
                build_plate_id=plate.id,
                maintenance_type=PlateMaintenanceType.CLEANED,
                performed_by=operator.id,
                source="legacy_web_route",
                occurred_at=now,
                created_at=now,
            )
        )
    if surface is not None:
        surface.last_mesh_calibrated_at = now
        surface.record_version += 1
        session.add(
            BuildPlateMaintenanceEvent(
                build_plate_id=plate.id,
                build_plate_surface_id=surface.id,
                maintenance_type=PlateMaintenanceType.MESH_CALIBRATED,
                performed_by=operator.id,
                source="legacy_web_route",
                occurred_at=now,
                created_at=now,
            )
        )
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
    return await build_plate_response(session, await _get_plate(session, plate.id))
