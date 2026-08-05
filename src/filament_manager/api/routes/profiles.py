"""Versioned material profile creation, publication, and Cura export."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from filament_manager.models.enums import ProfileStatus
from filament_manager.models.inventory import BuildPlate, FilamentProduct, MaterialProfile, Printer
from filament_manager.services.events import add_audit_event, add_outbox_job

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import ProfileCreate, ProfileResponse

router = APIRouter(prefix="/profiles", tags=["material profiles"])


def _profile_payload(profile: MaterialProfile) -> dict[str, object]:
    """Return stable export fields without ORM or internal timestamps."""

    return {
        "profile_id": str(profile.id),
        "version": profile.version,
        "filament_product_id": str(profile.filament_product_id),
        "printer_id": str(profile.printer_id),
        "nozzle_diameter_mm": str(profile.nozzle_diameter_mm),
        "chamber_temp_c": str(profile.chamber_temp_c) if profile.chamber_temp_c is not None else None,
        "extruder_temp_c": str(profile.extruder_temp_c),
        "bed_temp_c": str(profile.bed_temp_c),
        "flow_percent": str(profile.flow_percent),
        "print_speed_mm_s": str(profile.print_speed_mm_s) if profile.print_speed_mm_s else None,
        "retraction_distance_mm": str(profile.retraction_distance_mm)
        if profile.retraction_distance_mm is not None
        else None,
        "retraction_speed_mm_s": str(profile.retraction_speed_mm_s)
        if profile.retraction_speed_mm_s is not None
        else None,
        "cooling_enabled": profile.cooling_enabled,
        "cooling_min_percent": str(profile.cooling_min_percent),
        "cooling_max_percent": str(profile.cooling_max_percent),
        "support_overhang_angle_deg": str(profile.support_overhang_angle_deg)
        if profile.support_overhang_angle_deg is not None
        else None,
        "tree_max_branch_angle_deg": str(profile.tree_max_branch_angle_deg)
        if profile.tree_max_branch_angle_deg is not None
        else None,
        "pressure_advance": str(profile.pressure_advance) if profile.pressure_advance is not None else None,
        "filament_density_g_cm3": str(profile.filament_density_g_cm3),
        "preferred_build_plate_id": str(profile.preferred_build_plate_id)
        if profile.preferred_build_plate_id
        else None,
        "cura_extensions_schema_version": profile.cura_extensions_schema_version,
        "cura_extensions": profile.cura_extensions,
    }


@router.get("", response_model=list[ProfileResponse])
async def list_profiles(_: Viewer, session: DatabaseSession) -> list[ProfileResponse]:
    """List all material profile versions newest first."""

    result = await session.execute(
        select(MaterialProfile).order_by(MaterialProfile.updated_at.desc(), MaterialProfile.version.desc())
    )
    return [ProfileResponse.model_validate(profile) for profile in result.scalars()]


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfileCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> ProfileResponse:
    """Create a new draft version scoped to product, printer, and nozzle."""

    if await session.get(FilamentProduct, payload.filament_product_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_filament", "Filament not found")
    if await session.get(Printer, payload.printer_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_printer", "Printer not found")
    if (
        payload.preferred_build_plate_id
        and await session.get(BuildPlate, payload.preferred_build_plate_id) is None
    ):
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_build_plate", "Build plate not found")
    latest = await session.scalar(
        select(func.max(MaterialProfile.version)).where(
            MaterialProfile.filament_product_id == payload.filament_product_id,
            MaterialProfile.printer_id == payload.printer_id,
            MaterialProfile.nozzle_diameter_mm == payload.nozzle_diameter_mm,
        )
    )
    profile = MaterialProfile(
        **payload.model_dump(),
        version=(latest or 0) + 1,
        status=ProfileStatus.DRAFT,
    )
    session.add(profile)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="profile.create",
        object_type="material_profile",
        object_id=profile.id,
        before=None,
        after={"version": profile.version, "status": profile.status.value},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return ProfileResponse.model_validate(profile)


@router.post("/{profile_id}/publish", response_model=ProfileResponse)
async def publish_profile(
    profile_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> ProfileResponse:
    """Publish an immutable profile version and queue projections."""

    profile = await session.scalar(
        select(MaterialProfile).where(MaterialProfile.id == profile_id).with_for_update()
    )
    if profile is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_profile", "Profile not found")
    if profile.status == ProfileStatus.PUBLISHED:
        return ProfileResponse.model_validate(profile)
    if profile.status not in {ProfileStatus.DRAFT, ProfileStatus.VALIDATED}:
        raise ApiError(status.HTTP_409_CONFLICT, "profile_not_publishable", "Profile is not publishable")
    payload = _profile_payload(profile)
    checksum = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    profile.status = ProfileStatus.PUBLISHED
    profile.checksum = checksum
    profile.published_at = datetime.now(UTC)
    profile.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="profile.publish",
        object_type="material_profile",
        object_id=profile.id,
        before={"status": "draft"},
        after={"status": "published", "checksum": checksum},
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="google.profile.publish",
        idempotency_key=f"profile:{profile.id}:google:v{profile.record_version}",
        aggregate_type="material_profile",
        aggregate_id=profile.id,
        aggregate_version=profile.record_version,
        payload={"profile_id": str(profile.id)},
    )
    await session.commit()
    return ProfileResponse.model_validate(profile)


@router.get("/{profile_id}/exports/cura")
async def export_cura_profile(profile_id: UUID, _: Viewer, session: DatabaseSession) -> JSONResponse:
    """Export stable Cura-oriented keys with version and checksum metadata."""

    profile = await session.get(MaterialProfile, profile_id)
    if profile is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_profile", "Profile not found")
    if profile.status != ProfileStatus.PUBLISHED:
        raise ApiError(status.HTTP_409_CONFLICT, "profile_unpublished", "Publish the profile before export")
    data = _profile_payload(profile)
    data["checksum"] = profile.checksum
    cura_settings: dict[str, object] = dict(profile.cura_extensions)
    cura_settings.update(
        {
            "material_print_temperature": str(profile.extruder_temp_c),
            "material_bed_temperature": str(profile.bed_temp_c),
            "material_flow": str(profile.flow_percent),
            "retraction_amount": str(profile.retraction_distance_mm or 0),
            "retraction_speed": str(profile.retraction_speed_mm_s or 0),
            "cool_fan_enabled": profile.cooling_enabled,
            "cool_fan_speed_min": str(profile.cooling_min_percent),
            "cool_fan_speed": str(profile.cooling_max_percent),
            "support_angle": str(profile.support_overhang_angle_deg or 0),
            "material_density": str(profile.filament_density_g_cm3),
        }
    )
    data["cura"] = cura_settings
    return JSONResponse(data)
