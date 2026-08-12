"""Versioned material profile creation, publication, and Cura export."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from filament_manager.domain.cura_material_settings import (
    CURA_EXTENSION_SETTING_KEYS,
    cura_material_settings_catalog,
    cura_settings_for_profile,
)
from filament_manager.models.enums import ProfileStatus
from filament_manager.models.inventory import (
    BuildPlateSurface,
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
)
from filament_manager.models.workstations import WorkstationAgent
from filament_manager.services.cura_library import queue_cura_library
from filament_manager.services.events import add_audit_event, add_outbox_job

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    CuraMaterialImportRequest,
    MaterialTemplateCreate,
    MaterialTemplateResponse,
    MaterialTemplateRevisionCreate,
    MaterialTemplateRevisionResponse,
    MaterialTemplateUpdate,
    ProfileCreate,
    ProfileResponse,
)

router = APIRouter(prefix="/profiles", tags=["material profiles"])


@router.get("/cura-settings/catalog", response_model=list[dict[str, object]])
async def cura_settings_catalog(_: Viewer) -> list[dict[str, object]]:
    """Return the exact ordered Cura material setting catalog used by this deployment."""

    return cura_material_settings_catalog()


def _template_revision_response(
    revision: MaterialTemplateRevision,
) -> MaterialTemplateRevisionResponse:
    """Validate one stored JSON snapshot before returning it to a client."""

    return MaterialTemplateRevisionResponse(
        id=revision.id,
        material_template_id=revision.material_template_id,
        version=revision.version,
        status=revision.status,
        settings=revision.settings,
        checksum=revision.checksum,
        published_at=revision.published_at,
        record_version=revision.record_version,
        created_at=revision.created_at,
    )


async def _template_response(
    session: DatabaseSession,
    template: MaterialTemplate,
) -> MaterialTemplateResponse:
    """Return one template with all revisions newest first."""

    revisions = list(
        await session.scalars(
            select(MaterialTemplateRevision)
            .where(MaterialTemplateRevision.material_template_id == template.id)
            .order_by(MaterialTemplateRevision.version.desc())
        )
    )
    return MaterialTemplateResponse(
        id=template.id,
        name=template.name,
        material_type=template.material_type,
        description=template.description,
        printer_id=template.printer_id,
        nozzle_diameter_mm=template.nozzle_diameter_mm,
        filament_diameter_mm=template.filament_diameter_mm,
        active=template.active,
        record_version=template.record_version,
        created_at=template.created_at,
        updated_at=template.updated_at,
        revisions=[_template_revision_response(item) for item in revisions],
    )


@router.get("/templates", response_model=list[MaterialTemplateResponse])
async def list_material_templates(
    _: Viewer,
    session: DatabaseSession,
    include_inactive: bool = False,
) -> list[MaterialTemplateResponse]:
    """List reusable printer/nozzle templates and their immutable revisions."""

    query = select(MaterialTemplate).order_by(MaterialTemplate.material_type, MaterialTemplate.name)
    if not include_inactive:
        query = query.where(MaterialTemplate.active.is_(True))
    templates = list(await session.scalars(query))
    return [await _template_response(session, item) for item in templates]


@router.post(
    "/templates",
    response_model=MaterialTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_material_template(
    payload: MaterialTemplateCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> MaterialTemplateResponse:
    """Create a scoped material template and its initial draft revision."""

    if await session.get(Printer, payload.printer_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_printer", "Printer not found")
    if (
        payload.settings.preferred_build_plate_surface_id
        and await session.get(BuildPlateSurface, payload.settings.preferred_build_plate_surface_id) is None
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_build_plate_surface",
            "Build plate side not found",
        )
    existing = await session.scalar(
        select(MaterialTemplate.id).where(
            func.lower(MaterialTemplate.material_type) == payload.material_type.strip().casefold(),
            MaterialTemplate.printer_id == payload.printer_id,
            MaterialTemplate.nozzle_diameter_mm == payload.nozzle_diameter_mm,
        )
    )
    if existing is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "material_template_scope_exists",
            "A template already exists for this material, printer, and nozzle",
        )
    template = MaterialTemplate(
        name=payload.name.strip(),
        material_type=payload.material_type.strip(),
        description=payload.description,
        printer_id=payload.printer_id,
        nozzle_diameter_mm=payload.nozzle_diameter_mm,
        filament_diameter_mm=payload.filament_diameter_mm,
        active=True,
    )
    session.add(template)
    await session.flush()
    revision = MaterialTemplateRevision(
        material_template_id=template.id,
        version=1,
        status=ProfileStatus.DRAFT,
        settings=payload.settings.model_dump(mode="json"),
    )
    session.add(revision)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="material_template.create",
        object_type="material_template",
        object_id=template.id,
        before=None,
        after={"material_type": template.material_type, "revision_id": str(revision.id)},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return await _template_response(session, template)


@router.patch("/templates/{template_id}", response_model=MaterialTemplateResponse)
async def update_material_template(
    template_id: UUID,
    payload: MaterialTemplateUpdate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> MaterialTemplateResponse:
    """Update template identity metadata without changing any revision."""

    template = await session.scalar(
        select(MaterialTemplate).where(MaterialTemplate.id == template_id).with_for_update()
    )
    if template is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_template", "Template not found")
    if template.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "version_conflict", "Template was changed elsewhere")
    if payload.material_type is not None:
        conflicting_template = await session.scalar(
            select(MaterialTemplate.id).where(
                MaterialTemplate.id != template.id,
                func.lower(MaterialTemplate.material_type) == payload.material_type.strip().casefold(),
                MaterialTemplate.printer_id == template.printer_id,
                MaterialTemplate.nozzle_diameter_mm == template.nozzle_diameter_mm,
            )
        )
        if conflicting_template is not None:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "material_template_scope_exists",
                "A template already exists for this material, printer, and nozzle",
            )
    before: dict[str, object] = {
        "name": template.name,
        "material_type": template.material_type,
        "description": template.description,
        "active": template.active,
    }
    if payload.name is not None:
        template.name = payload.name.strip()
    if payload.material_type is not None:
        template.material_type = payload.material_type.strip()
    if "description" in payload.model_fields_set:
        template.description = payload.description
    if payload.active is not None:
        template.active = payload.active
    template.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="material_template.update",
        object_type="material_template",
        object_id=template.id,
        before=before,
        after={
            "name": template.name,
            "material_type": template.material_type,
            "description": template.description,
            "active": template.active,
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return await _template_response(session, template)


@router.post(
    "/templates/{template_id}/revisions",
    response_model=MaterialTemplateRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_material_template_revision(
    template_id: UUID,
    payload: MaterialTemplateRevisionCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> MaterialTemplateRevisionResponse:
    """Create the next complete draft revision for a reusable template."""

    template = await session.scalar(
        select(MaterialTemplate).where(MaterialTemplate.id == template_id).with_for_update()
    )
    if template is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_template", "Template not found")
    if template.record_version != payload.expected_template_version:
        raise ApiError(status.HTTP_409_CONFLICT, "version_conflict", "Template was changed elsewhere")
    latest = await session.scalar(
        select(func.max(MaterialTemplateRevision.version)).where(
            MaterialTemplateRevision.material_template_id == template.id
        )
    )
    revision = MaterialTemplateRevision(
        material_template_id=template.id,
        version=(latest or 0) + 1,
        status=ProfileStatus.DRAFT,
        settings=payload.settings.model_dump(mode="json"),
    )
    session.add(revision)
    template.record_version += 1
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="material_template.revision.create",
        object_type="material_template_revision",
        object_id=revision.id,
        before=None,
        after={"template_id": str(template.id), "version": revision.version},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return _template_revision_response(revision)


@router.post(
    "/templates/{template_id}/revisions/{revision_id}/publish",
    response_model=MaterialTemplateRevisionResponse,
)
async def publish_material_template_revision(
    template_id: UUID,
    revision_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> MaterialTemplateRevisionResponse:
    """Publish an immutable template revision for product creation and Cura sync."""

    revision = await session.scalar(
        select(MaterialTemplateRevision)
        .where(
            MaterialTemplateRevision.id == revision_id,
            MaterialTemplateRevision.material_template_id == template_id,
        )
        .with_for_update()
    )
    if revision is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_template_revision", "Revision not found")
    if revision.status == ProfileStatus.PUBLISHED:
        return _template_revision_response(revision)
    if revision.status not in {ProfileStatus.DRAFT, ProfileStatus.VALIDATED}:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "template_revision_not_publishable",
            "Template revision is not publishable",
        )
    snapshot = {
        "material_template_id": str(template_id),
        "version": revision.version,
        "settings": revision.settings,
    }
    checksum = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    revision.status = ProfileStatus.PUBLISHED
    revision.checksum = checksum
    revision.published_at = datetime.now(UTC)
    revision.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="material_template.revision.publish",
        object_type="material_template_revision",
        object_id=revision.id,
        before={"status": "draft"},
        after={"status": "published", "checksum": checksum},
        correlation_id=request.state.correlation_id,
    )
    managed_agents = list(
        await session.scalars(
            select(WorkstationAgent).where(
                WorkstationAgent.enabled.is_(True),
                WorkstationAgent.cura_management_enabled.is_(True),
            )
        )
    )
    if managed_agents:
        await queue_cura_library(session, managed_agents, requested_by=operator.id, force=True)
    await session.commit()
    return _template_revision_response(revision)


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
        "outer_wall_speed_mm_s": (
            str(profile.outer_wall_speed_mm_s) if profile.outer_wall_speed_mm_s else None
        ),
        "inner_wall_speed_mm_s": (
            str(profile.inner_wall_speed_mm_s) if profile.inner_wall_speed_mm_s else None
        ),
        "infill_speed_mm_s": str(profile.infill_speed_mm_s) if profile.infill_speed_mm_s else None,
        "top_bottom_speed_mm_s": (
            str(profile.top_bottom_speed_mm_s) if profile.top_bottom_speed_mm_s else None
        ),
        "initial_layer_speed_mm_s": (
            str(profile.initial_layer_speed_mm_s) if profile.initial_layer_speed_mm_s else None
        ),
        "travel_speed_mm_s": str(profile.travel_speed_mm_s) if profile.travel_speed_mm_s else None,
        "support_speed_mm_s": str(profile.support_speed_mm_s) if profile.support_speed_mm_s else None,
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
        "preferred_build_plate_surface_id": str(profile.preferred_build_plate_surface_id)
        if profile.preferred_build_plate_surface_id
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
        payload.preferred_build_plate_surface_id
        and await session.get(BuildPlateSurface, payload.preferred_build_plate_surface_id) is None
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_build_plate_surface",
            "Build plate side not found",
        )
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


def _import_decimal(
    settings: dict[str, object],
    *keys: str,
    required: bool = False,
) -> Decimal | None:
    """Read the first finite decimal setting without evaluating Cura expressions."""

    value = next((settings[key] for key in keys if settings.get(key) not in {None, ""}), None)
    if value is None:
        if required:
            raise ValueError(f"Cura material is missing required setting {keys[0]}")
        return None
    if isinstance(value, bool):
        raise ValueError(f"Cura material setting {keys[0]} must be numeric")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Cura material setting {keys[0]} must be a decimal value") from exc
    if not parsed.is_finite():
        raise ValueError(f"Cura material setting {keys[0]} must be finite")
    return parsed


def _import_boolean(settings: dict[str, object], key: str, *, default: bool) -> bool:
    """Read one explicit boolean without truthy string coercion."""

    value = settings.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if value in {"True", "true"}:
        return True
    if value in {"False", "false"}:
        return False
    raise ValueError(f"Cura material setting {key} must be a boolean")


@router.post(
    "/import-cura-material",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_cura_material(
    payload: CuraMaterialImportRequest,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> ProfileResponse:
    """Create a draft from one existing material reported by a paired workstation."""

    agent = await session.get(WorkstationAgent, payload.agent_id)
    if agent is None or not agent.enabled:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "workstation_unavailable",
            "Workstation is unavailable",
        )
    candidate = next(
        (material for material in agent.cura_materials if material.get("source_id") == payload.source_id),
        None,
    )
    if candidate is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "cura_material_unknown",
            "Cura material was not found on the selected workstation",
        )
    settings = candidate.get("settings")
    if not isinstance(settings, dict):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_material_invalid",
            "Cura material settings are invalid",
        )
    product = await session.get(FilamentProduct, payload.filament_product_id)
    if product is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_filament", "Filament not found")
    if await session.get(Printer, payload.printer_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_printer", "Printer not found")
    if (
        payload.preferred_build_plate_surface_id
        and await session.get(BuildPlateSurface, payload.preferred_build_plate_surface_id) is None
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_build_plate_surface",
            "Build plate side not found",
        )
    try:
        cooling_max = _import_decimal(settings, "cool_fan_speed_max", "cool_fan_speed")
        if cooling_max is None:
            cooling_max = Decimal("100")
        cooling_min = _import_decimal(settings, "cool_fan_speed_min")
        if cooling_min is None:
            cooling_min = cooling_max
        flow_percent = _import_decimal(settings, "material_flow")
        if flow_percent is None:
            flow_percent = Decimal("100")
        typed = {
            "chamber_temp_c": _import_decimal(settings, "build_volume_temperature"),
            "extruder_temp_c": _import_decimal(
                settings,
                "material_print_temperature",
                "default_material_print_temperature",
                required=True,
            ),
            "bed_temp_c": _import_decimal(
                settings,
                "material_bed_temperature",
                "default_material_bed_temperature",
                required=True,
            ),
            "flow_percent": flow_percent,
            "print_speed_mm_s": _import_decimal(settings, "speed_print"),
            "outer_wall_speed_mm_s": _import_decimal(settings, "speed_wall_0"),
            "inner_wall_speed_mm_s": _import_decimal(settings, "speed_wall_x"),
            "infill_speed_mm_s": _import_decimal(settings, "speed_infill"),
            "top_bottom_speed_mm_s": _import_decimal(settings, "speed_topbottom"),
            "initial_layer_speed_mm_s": _import_decimal(settings, "speed_print_layer_0", "speed_layer_0"),
            "travel_speed_mm_s": _import_decimal(settings, "speed_travel"),
            "support_speed_mm_s": _import_decimal(settings, "speed_support"),
            "retraction_distance_mm": _import_decimal(settings, "retraction_amount"),
            "retraction_speed_mm_s": _import_decimal(settings, "retraction_speed"),
            "cooling_enabled": _import_boolean(settings, "cool_fan_enabled", default=True),
            "cooling_min_percent": cooling_min,
            "cooling_max_percent": cooling_max,
            "support_overhang_angle_deg": _import_decimal(settings, "support_angle"),
            "pressure_advance": _import_decimal(settings, "klipper_pressure_advance_factor"),
        }
        extensions = {key: value for key, value in settings.items() if key in CURA_EXTENSION_SETTING_KEYS}
        profile_input = ProfileCreate(
            filament_product_id=payload.filament_product_id,
            printer_id=payload.printer_id,
            nozzle_diameter_mm=payload.nozzle_diameter_mm,
            filament_density_g_cm3=product.density_g_cm3,
            preferred_build_plate_surface_id=payload.preferred_build_plate_surface_id,
            cura_extensions=extensions,
            **typed,
        )
    except ValueError as exc:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_material_invalid",
            str(exc),
        ) from exc
    latest = await session.scalar(
        select(func.max(MaterialProfile.version)).where(
            MaterialProfile.filament_product_id == profile_input.filament_product_id,
            MaterialProfile.printer_id == profile_input.printer_id,
            MaterialProfile.nozzle_diameter_mm == profile_input.nozzle_diameter_mm,
        )
    )
    profile = MaterialProfile(
        **profile_input.model_dump(),
        version=(latest or 0) + 1,
        status=ProfileStatus.DRAFT,
    )
    session.add(profile)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="profile.import_cura_material",
        object_type="material_profile",
        object_id=profile.id,
        before=None,
        after={
            "version": profile.version,
            "status": profile.status.value,
            "workstation_agent_id": str(agent.id),
            "cura_material_source_id": payload.source_id,
        },
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
    managed_agents = list(
        await session.scalars(
            select(WorkstationAgent).where(
                WorkstationAgent.enabled.is_(True),
                WorkstationAgent.cura_management_enabled.is_(True),
            )
        )
    )
    if managed_agents:
        await queue_cura_library(session, managed_agents, requested_by=operator.id, force=True)
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
    data["cura"] = cura_settings_for_profile(profile)
    return JSONResponse(data)
