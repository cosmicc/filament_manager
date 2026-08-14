"""Versioned material profile creation, publication, and Cura export."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from filament_manager.domain.cura_import import material_settings_from_cura
from filament_manager.domain.cura_material_settings import (
    cura_material_settings_catalog,
    cura_settings_for_profile,
)
from filament_manager.domain.profile_inheritance import (
    override_setting_keys,
    profile_columns_from_settings,
    resolve_profile_settings,
    settings_snapshot_from_profile,
    sparse_profile_overrides,
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
    CuraMaterialTemplateImportRequest,
    MaterialSettingsInput,
    MaterialTemplateCreate,
    MaterialTemplateResponse,
    MaterialTemplateRevisionCreate,
    MaterialTemplateRevisionResponse,
    MaterialTemplateUpdate,
    ProfileCreate,
    ProfileResponse,
    ProfileRevisionCreate,
    ProfileTemplateRebaseRequest,
)

router = APIRouter(prefix="/profiles", tags=["material profiles"])


def _template_name(material_type: str) -> str:
    """Return the canonical template identity shown in the app and Cura."""

    return f"Template {material_type.strip()}"


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
        source_workstation_agent_id=template.source_workstation_agent_id,
        source_cura_material_id=template.source_cura_material_id,
        active=template.active,
        record_version=template.record_version,
        created_at=template.created_at,
        updated_at=template.updated_at,
        revisions=[_template_revision_response(item) for item in revisions],
    )


async def _profile_base(
    session: DatabaseSession,
    profile: MaterialProfile,
) -> tuple[MaterialTemplateRevision, MaterialTemplate]:
    """Load the required active template relationship for one material profile."""

    revision = (
        await session.get(MaterialTemplateRevision, profile.base_template_revision_id)
        if profile.base_template_revision_id
        else None
    )
    template = await session.get(MaterialTemplate, revision.material_template_id) if revision else None
    if revision is None or template is None:
        raise RuntimeError("A material profile is missing its template base")
    return revision, template


def _template_update_changes(
    current: dict[str, object],
    proposed: dict[str, object],
    override_keys: set[str],
) -> list[dict[str, object]]:
    """Describe effective per-setting changes for an explicit base update."""

    differences = sparse_profile_overrides(current, proposed)
    rows = [
        {
            "key": key,
            "current_value": current.get(key),
            "proposed_value": proposed.get(key),
            "overridden": key in override_keys,
        }
        for key in differences
        if key != "cura_extensions"
    ]
    extension_changes = differences.get("cura_extensions")
    current_extensions = current.get("cura_extensions", {})
    proposed_extensions = proposed.get("cura_extensions", {})
    if isinstance(extension_changes, dict):
        assert isinstance(current_extensions, dict)
        assert isinstance(proposed_extensions, dict)
        rows.extend(
            {
                "key": key,
                "current_value": current_extensions.get(key),
                "proposed_value": proposed_extensions.get(key),
                "overridden": key in override_keys,
            }
            for key in extension_changes
        )
    return sorted(rows, key=lambda row: str(row["key"]))


async def _profile_response(
    session: DatabaseSession,
    profile: MaterialProfile,
) -> ProfileResponse:
    """Return resolved settings, sparse ownership, and template-update context."""

    base_revision, template = await _profile_base(session, profile)
    latest_revision = await session.scalar(
        select(MaterialTemplateRevision)
        .where(
            MaterialTemplateRevision.material_template_id == template.id,
            MaterialTemplateRevision.status == ProfileStatus.PUBLISHED,
        )
        .order_by(MaterialTemplateRevision.version.desc())
        .limit(1)
    )
    current = settings_snapshot_from_profile(profile)
    overrides = dict(profile.setting_overrides or {})
    customized_keys = override_setting_keys(overrides)
    changes: list[dict[str, object]] = []
    if latest_revision is not None and latest_revision.id != base_revision.id:
        proposed = resolve_profile_settings(latest_revision.settings, overrides)
        changes = _template_update_changes(current, proposed, customized_keys)
    settings = MaterialSettingsInput.model_validate(current)
    return ProfileResponse(
        **settings.model_dump(),
        id=profile.id,
        filament_product_id=profile.filament_product_id,
        printer_id=profile.printer_id,
        nozzle_diameter_mm=profile.nozzle_diameter_mm,
        version=profile.version,
        status=profile.status,
        checksum=profile.checksum,
        published_at=profile.published_at,
        record_version=profile.record_version,
        base_template_revision_id=base_revision.id,
        setting_overrides=overrides,
        override_keys=sorted(customized_keys),
        override_count=len(customized_keys),
        inheritance_status="customized" if customized_keys else "inherited",
        base_template_id=template.id,
        base_template_name=template.name,
        base_template_version=base_revision.version,
        base_template_settings=base_revision.settings,
        latest_template_revision_id=latest_revision.id if latest_revision else base_revision.id,
        latest_template_version=latest_revision.version if latest_revision else base_revision.version,
        template_update_changes=changes,
        source_workstation_agent_id=profile.source_workstation_agent_id,
        source_cura_material_id=profile.source_cura_material_id,
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
            MaterialTemplate.active.is_(True),
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
        name=_template_name(payload.material_type),
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


@router.post(
    "/templates/import-cura-material",
    response_model=MaterialTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_cura_material_template(
    payload: CuraMaterialTemplateImportRequest,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> MaterialTemplateResponse:
    """Preserve one reported Cura material as a reviewable draft template."""

    agent, candidate, settings = await _reported_cura_material(
        session,
        agent_id=payload.agent_id,
        source_id=payload.source_id,
    )
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
    imported_template = await session.scalar(
        select(MaterialTemplate.id).where(
            MaterialTemplate.source_workstation_agent_id == agent.id,
            MaterialTemplate.source_cura_material_id == payload.source_id,
        )
    )
    imported_profile = await session.scalar(
        select(MaterialProfile.id).where(
            MaterialProfile.source_workstation_agent_id == agent.id,
            MaterialProfile.source_cura_material_id == payload.source_id,
        )
    )
    if imported_template is not None or imported_profile is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_material_already_imported",
            "This Cura material has already been imported",
        )
    existing_scope = await session.scalar(
        select(MaterialTemplate.id).where(
            MaterialTemplate.active.is_(True),
            func.lower(MaterialTemplate.material_type) == payload.material_type.strip().casefold(),
            MaterialTemplate.printer_id == payload.printer_id,
            MaterialTemplate.nozzle_diameter_mm == payload.nozzle_diameter_mm,
        )
    )
    if existing_scope is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "material_template_scope_exists",
            "A template already exists for this material, printer, and nozzle; "
            "import this source as a filament profile",
        )
    try:
        imported_settings = MaterialSettingsInput.model_validate(
            material_settings_from_cura(
                settings,
                filament_density_g_cm3=payload.filament_density_g_cm3,
                preferred_build_plate_surface_id=payload.preferred_build_plate_surface_id,
            )
        )
    except ValueError as exc:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_material_invalid",
            str(exc),
        ) from exc
    candidate_name = str(candidate.get("name") or payload.name).strip()
    template = MaterialTemplate(
        name=_template_name(payload.material_type),
        material_type=payload.material_type.strip(),
        description=payload.description
        or (
            f'Imported from Cura material "{candidate_name}" on {agent.display_name}. '
            "Review before publishing."
        ),
        printer_id=payload.printer_id,
        nozzle_diameter_mm=payload.nozzle_diameter_mm,
        filament_diameter_mm=payload.filament_diameter_mm,
        source_workstation_agent_id=agent.id,
        source_cura_material_id=payload.source_id,
        active=True,
    )
    session.add(template)
    await session.flush()
    revision = MaterialTemplateRevision(
        material_template_id=template.id,
        version=1,
        status=ProfileStatus.DRAFT,
        settings=imported_settings.model_dump(mode="json"),
    )
    session.add(revision)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="material_template.import_cura_material",
        object_type="material_template",
        object_id=template.id,
        before=None,
        after={
            "material_type": template.material_type,
            "revision_id": str(revision.id),
            "status": revision.status.value,
            "workstation_agent_id": str(agent.id),
            "cura_material_source_id": payload.source_id,
        },
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
    target_material_type = (
        payload.material_type.strip() if payload.material_type is not None else template.material_type
    )
    target_active = payload.active if payload.active is not None else template.active
    if target_active:
        conflicting_template = await session.scalar(
            select(MaterialTemplate.id).where(
                MaterialTemplate.id != template.id,
                MaterialTemplate.active.is_(True),
                func.lower(MaterialTemplate.material_type) == target_material_type.casefold(),
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
    if payload.material_type is not None:
        template.material_type = payload.material_type.strip()
    template.name = _template_name(template.material_type)
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
        "base_template_revision_id": (
            str(profile.base_template_revision_id) if profile.base_template_revision_id else None
        ),
        "setting_overrides": profile.setting_overrides,
    }


async def _validate_profile_base(
    session: DatabaseSession,
    *,
    revision_id: UUID | None,
    product: FilamentProduct,
    printer_id: UUID,
    nozzle_diameter_mm: Decimal,
) -> tuple[MaterialTemplateRevision, MaterialTemplate]:
    """Require one published matching template revision as a profile base."""

    revision = await session.get(MaterialTemplateRevision, revision_id) if revision_id else None
    template = await session.get(MaterialTemplate, revision.material_template_id) if revision else None
    if revision is None or revision.status != ProfileStatus.PUBLISHED or template is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "profile_template_required",
            "Select a published material template revision",
        )
    if not template.active:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "material_template_inactive",
            "The selected material template is inactive",
        )
    if (
        template.material_type.casefold() != product.material_type.casefold()
        or template.printer_id != printer_id
        or template.nozzle_diameter_mm != nozzle_diameter_mm
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "profile_template_scope_mismatch",
            "The template material, printer, and nozzle must match the profile",
        )
    return revision, template


@router.get("", response_model=list[ProfileResponse])
async def list_profiles(_: Viewer, session: DatabaseSession) -> list[ProfileResponse]:
    """List all material profile versions newest first."""

    result = await session.execute(
        select(MaterialProfile).order_by(MaterialProfile.updated_at.desc(), MaterialProfile.version.desc())
    )
    return [await _profile_response(session, profile) for profile in result.scalars()]


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfileCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> ProfileResponse:
    """Create a new draft version scoped to product, printer, and nozzle."""

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
    base_revision, _ = await _validate_profile_base(
        session,
        revision_id=payload.base_template_revision_id or product.source_template_revision_id,
        product=product,
        printer_id=payload.printer_id,
        nozzle_diameter_mm=payload.nozzle_diameter_mm,
    )
    desired_settings = MaterialSettingsInput.model_validate(payload).model_dump(mode="json")
    latest = await session.scalar(
        select(func.max(MaterialProfile.version)).where(
            MaterialProfile.filament_product_id == payload.filament_product_id,
            MaterialProfile.printer_id == payload.printer_id,
            MaterialProfile.nozzle_diameter_mm == payload.nozzle_diameter_mm,
        )
    )
    profile = MaterialProfile(
        **profile_columns_from_settings(desired_settings),
        filament_product_id=payload.filament_product_id,
        printer_id=payload.printer_id,
        nozzle_diameter_mm=payload.nozzle_diameter_mm,
        version=(latest or 0) + 1,
        status=ProfileStatus.DRAFT,
        base_template_revision_id=base_revision.id,
        setting_overrides=sparse_profile_overrides(base_revision.settings, desired_settings),
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
    return await _profile_response(session, profile)


@router.post(
    "/{profile_id}/revisions",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile_revision(
    profile_id: UUID,
    payload: ProfileRevisionCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> ProfileResponse:
    """Create a new editable draft without mutating the selected profile snapshot."""

    source = await session.scalar(
        select(MaterialProfile).where(MaterialProfile.id == profile_id).with_for_update()
    )
    if source is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_profile", "Profile not found")
    if source.record_version != payload.expected_profile_version:
        raise ApiError(status.HTTP_409_CONFLICT, "version_conflict", "Profile changed; reload and retry")
    if (
        payload.settings.preferred_build_plate_surface_id
        and await session.get(
            BuildPlateSurface,
            payload.settings.preferred_build_plate_surface_id,
        )
        is None
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_build_plate_surface",
            "Build plate side not found",
        )
    base_revision, _ = await _profile_base(session, source)
    desired_settings = payload.settings.model_dump(mode="json")
    latest = await session.scalar(
        select(func.max(MaterialProfile.version)).where(
            MaterialProfile.filament_product_id == source.filament_product_id,
            MaterialProfile.printer_id == source.printer_id,
            MaterialProfile.nozzle_diameter_mm == source.nozzle_diameter_mm,
        )
    )
    revision = MaterialProfile(
        **profile_columns_from_settings(desired_settings),
        filament_product_id=source.filament_product_id,
        printer_id=source.printer_id,
        nozzle_diameter_mm=source.nozzle_diameter_mm,
        version=(latest or 0) + 1,
        status=ProfileStatus.DRAFT,
        base_template_revision_id=base_revision.id,
        setting_overrides=sparse_profile_overrides(base_revision.settings, desired_settings),
    )
    session.add(revision)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="profile.revision.create",
        object_type="material_profile",
        object_id=revision.id,
        before={"source_profile_id": str(source.id), "source_version": source.version},
        after={"version": revision.version, "status": revision.status.value},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return await _profile_response(session, revision)


async def _reported_cura_material(
    session: DatabaseSession,
    *,
    agent_id: UUID,
    source_id: str,
) -> tuple[WorkstationAgent, dict[str, object], dict[str, object]]:
    """Load one still-reported sanitized Cura material from an enabled agent."""

    agent = await session.get(WorkstationAgent, agent_id)
    if agent is None or not agent.enabled:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "workstation_unavailable",
            "Workstation is unavailable",
        )
    candidate = next(
        (material for material in agent.cura_materials if material.get("source_id") == source_id),
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
    return agent, candidate, settings


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

    agent, _, settings = await _reported_cura_material(
        session,
        agent_id=payload.agent_id,
        source_id=payload.source_id,
    )
    imported_template = await session.scalar(
        select(MaterialTemplate.id).where(
            MaterialTemplate.source_workstation_agent_id == agent.id,
            MaterialTemplate.source_cura_material_id == payload.source_id,
        )
    )
    imported_profile = await session.scalar(
        select(MaterialProfile.id).where(
            MaterialProfile.source_workstation_agent_id == agent.id,
            MaterialProfile.source_cura_material_id == payload.source_id,
        )
    )
    if imported_template is not None or imported_profile is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_material_already_imported",
            "This Cura material has already been imported",
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
        imported_settings = MaterialSettingsInput.model_validate(
            material_settings_from_cura(
                settings,
                filament_density_g_cm3=product.density_g_cm3,
                preferred_build_plate_surface_id=payload.preferred_build_plate_surface_id,
            )
        )
        profile_input = ProfileCreate(
            **imported_settings.model_dump(),
            filament_product_id=payload.filament_product_id,
            printer_id=payload.printer_id,
            nozzle_diameter_mm=payload.nozzle_diameter_mm,
            base_template_revision_id=product.source_template_revision_id,
        )
    except ValueError as exc:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_material_invalid",
            str(exc),
        ) from exc
    base_revision, _ = await _validate_profile_base(
        session,
        revision_id=profile_input.base_template_revision_id,
        product=product,
        printer_id=profile_input.printer_id,
        nozzle_diameter_mm=profile_input.nozzle_diameter_mm,
    )
    desired_settings = imported_settings.model_dump(mode="json")
    latest = await session.scalar(
        select(func.max(MaterialProfile.version)).where(
            MaterialProfile.filament_product_id == profile_input.filament_product_id,
            MaterialProfile.printer_id == profile_input.printer_id,
            MaterialProfile.nozzle_diameter_mm == profile_input.nozzle_diameter_mm,
        )
    )
    profile = MaterialProfile(
        **profile_columns_from_settings(desired_settings),
        filament_product_id=profile_input.filament_product_id,
        printer_id=profile_input.printer_id,
        nozzle_diameter_mm=profile_input.nozzle_diameter_mm,
        version=(latest or 0) + 1,
        status=ProfileStatus.DRAFT,
        base_template_revision_id=base_revision.id,
        setting_overrides=sparse_profile_overrides(base_revision.settings, desired_settings),
        source_workstation_agent_id=agent.id,
        source_cura_material_id=payload.source_id,
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
    return await _profile_response(session, profile)


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
        return await _profile_response(session, profile)
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
    return await _profile_response(session, profile)


@router.post(
    "/{profile_id}/template-base",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_profile_template_base(
    profile_id: UUID,
    payload: ProfileTemplateRebaseRequest,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> ProfileResponse:
    """Create one draft after explicit confirmation for one filament profile."""

    source = await session.scalar(
        select(MaterialProfile).where(MaterialProfile.id == profile_id).with_for_update()
    )
    if source is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_profile", "Profile not found")
    if source.record_version != payload.expected_profile_version:
        raise ApiError(status.HTTP_409_CONFLICT, "version_conflict", "Profile changed; reload and retry")
    current_base, template = await _profile_base(session, source)
    target = await session.get(MaterialTemplateRevision, payload.target_template_revision_id)
    if (
        target is None
        or target.material_template_id != template.id
        or target.status != ProfileStatus.PUBLISHED
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "template_base_unavailable",
            "Select a published revision of this profile's linked template",
        )
    if target.id == current_base.id:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "template_base_unchanged",
            "This profile already uses the selected template revision",
        )
    proposed = resolve_profile_settings(target.settings, source.setting_overrides)
    proposed_input = MaterialSettingsInput.model_validate(proposed)
    latest = await session.scalar(
        select(func.max(MaterialProfile.version)).where(
            MaterialProfile.filament_product_id == source.filament_product_id,
            MaterialProfile.printer_id == source.printer_id,
            MaterialProfile.nozzle_diameter_mm == source.nozzle_diameter_mm,
        )
    )
    new_overrides = sparse_profile_overrides(
        target.settings,
        proposed_input.model_dump(mode="json"),
    )
    revision = MaterialProfile(
        **profile_columns_from_settings(proposed_input.model_dump(mode="json")),
        filament_product_id=source.filament_product_id,
        printer_id=source.printer_id,
        nozzle_diameter_mm=source.nozzle_diameter_mm,
        version=(latest or 0) + 1,
        status=ProfileStatus.DRAFT,
        base_template_revision_id=target.id,
        setting_overrides=new_overrides,
    )
    session.add(revision)
    await session.flush()
    changes = _template_update_changes(
        settings_snapshot_from_profile(source),
        proposed_input.model_dump(mode="json"),
        override_setting_keys(source.setting_overrides),
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="profile.template_base.confirm",
        object_type="material_profile",
        object_id=revision.id,
        before={
            "source_profile_id": str(source.id),
            "base_template_revision_id": str(current_base.id),
        },
        after={
            "base_template_revision_id": str(target.id),
            "version": revision.version,
            "status": "draft",
            "effective_change_count": len(changes),
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return await _profile_response(session, revision)


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
