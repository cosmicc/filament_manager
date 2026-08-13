"""Resumable seven-step calibration workflow routes."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from filament_manager.domain.calibration import CALIBRATION_STEPS, invalidated_statuses, ready_to_publish
from filament_manager.domain.dimensional_calibration import (
    DimensionalCalibrationError,
    calculate_dimensional_compensation,
)
from filament_manager.domain.profile_inheritance import (
    profile_columns_from_settings,
    settings_snapshot_from_profile,
    sparse_profile_overrides,
)
from filament_manager.models.calibration import CalibrationSession, CalibrationStep
from filament_manager.models.enums import CalibrationStatus, CalibrationStepStatus, ProfileStatus
from filament_manager.models.inventory import (
    BuildPlate,
    BuildPlateSurface,
    FilamentProduct,
    MaterialProfile,
    MaterialTemplateRevision,
    Printer,
)
from filament_manager.services.events import add_audit_event, add_outbox_job

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    CalibrationCreate,
    CalibrationResponse,
    CalibrationStepUpdate,
    MaterialSettingsInput,
    ProfileResponse,
)

router = APIRouter(prefix="/calibrations", tags=["calibration"])


async def _get_calibration(
    session: DatabaseSession, calibration_id: UUID, *, lock: bool = False
) -> CalibrationSession:
    query = (
        select(CalibrationSession)
        .where(CalibrationSession.id == calibration_id)
        .options(selectinload(CalibrationSession.steps))
    )
    if lock:
        query = query.with_for_update()
    result = await session.execute(query)
    calibration = result.scalar_one_or_none()
    if calibration is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_calibration", "Calibration not found")
    return calibration


@router.get("", response_model=list[CalibrationResponse])
async def list_calibrations(_: Viewer, session: DatabaseSession) -> list[CalibrationResponse]:
    """List calibration sessions with their persistent ordered steps."""

    result = await session.execute(
        select(CalibrationSession)
        .options(selectinload(CalibrationSession.steps))
        .order_by(CalibrationSession.updated_at.desc())
    )
    return [CalibrationResponse.model_validate(item) for item in result.scalars()]


@router.post("", response_model=CalibrationResponse, status_code=status.HTTP_201_CREATED)
async def create_calibration(
    payload: CalibrationCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> CalibrationResponse:
    """Start a calibration session with the exact seven supplied steps."""

    if await session.get(FilamentProduct, payload.filament_product_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_filament", "Filament not found")
    if await session.get(Printer, payload.printer_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_printer", "Printer not found")
    build_plate_id = payload.build_plate_id
    if payload.build_plate_surface_id is not None:
        surface = await session.get(BuildPlateSurface, payload.build_plate_surface_id)
        if surface is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "unknown_build_plate_surface",
                "Build plate side not found",
            )
        if build_plate_id is not None and surface.build_plate_id != build_plate_id:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "build_plate_surface_mismatch",
                "Build plate side does not belong to the selected physical plate",
            )
        build_plate_id = surface.build_plate_id
    elif build_plate_id is not None and await session.get(BuildPlate, build_plate_id) is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unknown_build_plate",
            "Build plate not found",
        )
    baseline_profile_id = payload.baseline_profile_id
    if baseline_profile_id is None:
        baseline_profile_id = await session.scalar(
            select(MaterialProfile.id)
            .where(
                MaterialProfile.filament_product_id == payload.filament_product_id,
                MaterialProfile.printer_id == payload.printer_id,
                MaterialProfile.nozzle_diameter_mm == payload.nozzle_diameter_mm,
            )
            .order_by(MaterialProfile.version.desc())
            .limit(1)
        )
    elif not await session.scalar(
        select(MaterialProfile.id).where(
            MaterialProfile.id == baseline_profile_id,
            MaterialProfile.filament_product_id == payload.filament_product_id,
            MaterialProfile.printer_id == payload.printer_id,
            MaterialProfile.nozzle_diameter_mm == payload.nozzle_diameter_mm,
        )
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "baseline_profile_mismatch",
            "Baseline profile does not match the selected filament, printer, and nozzle",
        )
    calibration_data = payload.model_dump()
    calibration_data["build_plate_id"] = build_plate_id
    calibration_data["baseline_profile_id"] = baseline_profile_id
    calibration = CalibrationSession(
        **calibration_data,
        status=CalibrationStatus.IN_PROGRESS,
        operator_id=operator.id,
        started_at=datetime.now(UTC),
    )
    session.add(calibration)
    await session.flush()
    for definition in CALIBRATION_STEPS:
        session.add(
            CalibrationStep(
                session_id=calibration.id,
                step_order=definition.order,
                step_key=definition.key,
                name=definition.name,
                required=definition.required,
                status=CalibrationStepStatus.NOT_STARTED,
                affected_profile_fields=list(definition.profile_outputs),
            )
        )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="calibration.create",
        object_type="calibration_session",
        object_id=calibration.id,
        before=None,
        after={"status": calibration.status.value},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return CalibrationResponse.model_validate(await _get_calibration(session, calibration.id))


@router.get("/{calibration_id}", response_model=CalibrationResponse)
async def get_calibration(calibration_id: UUID, _: Viewer, session: DatabaseSession) -> CalibrationResponse:
    """Return a resumable session and all seven steps."""

    return CalibrationResponse.model_validate(await _get_calibration(session, calibration_id))


@router.post("/{calibration_id}/steps/{step_key}/start", response_model=CalibrationResponse)
async def start_step(
    calibration_id: UUID,
    step_key: str,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> CalibrationResponse:
    """Start an available step only after earlier required steps complete."""

    calibration = await _get_calibration(session, calibration_id, lock=True)
    step = next((item for item in calibration.steps if item.step_key == step_key), None)
    if step is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_calibration_step", "Calibration step not found")
    blockers = [
        item
        for item in calibration.steps
        if item.step_order < step.step_order
        and item.required
        and item.status != CalibrationStepStatus.COMPLETED
    ]
    if blockers:
        raise ApiError(
            status.HTTP_409_CONFLICT, "calibration_order_violation", "Complete earlier required steps first"
        )
    if step.status not in {CalibrationStepStatus.NOT_STARTED, CalibrationStepStatus.NEEDS_REVIEW}:
        raise ApiError(status.HTTP_409_CONFLICT, "calibration_step_unavailable", "Step cannot be started")
    step.status = CalibrationStepStatus.IN_PROGRESS
    step.record_version += 1
    calibration.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="calibration.step.start",
        object_type="calibration_step",
        object_id=step.id,
        before=None,
        after={"step_key": step.step_key, "status": step.status.value},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return CalibrationResponse.model_validate(calibration)


@router.post("/{calibration_id}/steps/{step_key}/result", response_model=CalibrationResponse)
async def update_step_result(
    calibration_id: UUID,
    step_key: str,
    payload: CalibrationStepUpdate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> CalibrationResponse:
    """Save a step result, repeat it, and invalidate completed dependants."""

    calibration = await _get_calibration(session, calibration_id, lock=True)
    step = next((item for item in calibration.steps if item.step_key == step_key), None)
    if step is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_calibration_step", "Calibration step not found")
    if step.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "record_version_conflict", "Step changed; reload and retry")
    if payload.repeat:
        changes = invalidated_statuses(
            [(item.step_order, item.status) for item in calibration.steps], step.step_order
        )
        for item in calibration.steps:
            if item.step_order in changes:
                item.status = changes[item.step_order]
                item.record_version += 1
        step.status = CalibrationStepStatus.IN_PROGRESS
        step.result = {}
        step.completed_at = None
    step.inputs = payload.inputs
    result = payload.result
    if step.step_key == "dimensional" and payload.complete:
        try:
            dimensional = calculate_dimensional_compensation(payload.inputs)
        except DimensionalCalibrationError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "dimensional_measurements_invalid",
                str(exc),
            ) from exc
        result = {
            "xy_offset": format(dimensional.xy_offset, "f"),
            "hole_xy_offset": format(dimensional.hole_xy_offset, "f"),
            "x_horizontal_expansion_mm": format(dimensional.x_horizontal_expansion, "f"),
            "y_horizontal_expansion_mm": format(dimensional.y_horizontal_expansion, "f"),
            "axis_difference_mm": format(dimensional.axis_difference, "f"),
            "axis_warning": dimensional.axis_warning,
        }
    step.result = result
    step.artifact = payload.artifact
    step.notes = payload.notes
    if payload.complete:
        if not result:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "calibration_result_required", "Result is required"
            )
        step.status = CalibrationStepStatus.COMPLETED
        step.completed_at = datetime.now(UTC)
    elif step.status == CalibrationStepStatus.NOT_STARTED:
        step.status = CalibrationStepStatus.IN_PROGRESS
    step.record_version += 1
    calibration.record_version += 1
    statuses = {item.step_key: item.status for item in calibration.steps}
    calibration.status = (
        CalibrationStatus.READY_TO_PUBLISH if ready_to_publish(statuses) else CalibrationStatus.IN_PROGRESS
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="calibration.step.update",
        object_type="calibration_step",
        object_id=step.id,
        before=None,
        after={"step_key": step.step_key, "status": step.status.value, "repeat": payload.repeat},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return CalibrationResponse.model_validate(calibration)


def _combined_results(calibration: CalibrationSession) -> dict[str, object]:
    combined: dict[str, object] = {}
    for step in calibration.steps:
        if step.status == CalibrationStepStatus.COMPLETED:
            combined.update(step.result)
    return combined


def _decimal_result(results: dict[str, object], key: str, default: Decimal | None = None) -> Decimal | None:
    """Convert a JSON calibration result into a database-safe decimal."""

    value = results.get(key)
    if value is None:
        return default
    return Decimal(str(value))


@router.post("/{calibration_id}/publish-profile", response_model=ProfileResponse)
async def publish_calibration_profile(
    calibration_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
    override_reason: str | None = None,
) -> ProfileResponse:
    """Publish an immutable material profile from completed step results."""

    calibration = await _get_calibration(session, calibration_id, lock=True)
    if calibration.status != CalibrationStatus.READY_TO_PUBLISH and not override_reason:
        raise ApiError(
            status.HTTP_409_CONFLICT, "profile_incomplete", "Mandatory calibration steps are incomplete"
        )
    results = _combined_results(calibration)
    product = await session.get(FilamentProduct, calibration.filament_product_id)
    assert product is not None
    required = {
        "extruder_temp_c",
        "bed_temp_c",
        "flow_percent",
        "retraction_distance_mm",
        "retraction_speed_mm_s",
        "support_overhang_angle_deg",
        "tree_max_branch_angle_deg",
        "pressure_advance",
        "xy_offset",
        "hole_xy_offset",
    }
    missing = sorted(required - results.keys())
    if missing and not override_reason:
        raise ApiError(
            status.HTTP_409_CONFLICT, "profile_incomplete", f"Missing profile fields: {', '.join(missing)}"
        )
    latest = await session.scalar(
        select(MaterialProfile.version)
        .where(
            MaterialProfile.filament_product_id == calibration.filament_product_id,
            MaterialProfile.printer_id == calibration.printer_id,
            MaterialProfile.nozzle_diameter_mm == calibration.nozzle_diameter_mm,
        )
        .order_by(MaterialProfile.version.desc())
        .limit(1)
    )
    baseline = (
        await session.get(MaterialProfile, calibration.baseline_profile_id)
        if calibration.baseline_profile_id
        else None
    )
    base_revision_id = (
        baseline.base_template_revision_id if baseline is not None else product.source_template_revision_id
    )
    base_revision = (
        await session.get(MaterialTemplateRevision, base_revision_id) if base_revision_id else None
    )
    if base_revision is None or base_revision.status != ProfileStatus.PUBLISHED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "profile_template_required",
            "Link this filament to a published template before publishing calibration results",
        )
    base_settings = (
        settings_snapshot_from_profile(baseline) if baseline is not None else dict(base_revision.settings)
    )
    for key in (
        "chamber_temp_c",
        "extruder_temp_c",
        "bed_temp_c",
        "flow_percent",
        "retraction_distance_mm",
        "retraction_speed_mm_s",
        "cooling_min_percent",
        "cooling_max_percent",
        "support_overhang_angle_deg",
        "tree_max_branch_angle_deg",
        "pressure_advance",
    ):
        if key in results:
            base_settings[key] = _decimal_result(results, key)
    if "cooling_enabled" in results:
        base_settings["cooling_enabled"] = bool(results["cooling_enabled"])
    raw_extensions = base_settings.get("cura_extensions", {})
    extensions = dict(raw_extensions) if isinstance(raw_extensions, dict) else {}
    for key in ("xy_offset", "hole_xy_offset"):
        if key in results:
            extensions[key] = format(Decimal(str(results[key])), "f")
    base_settings["cura_extensions"] = extensions
    base_settings["filament_density_g_cm3"] = product.density_g_cm3
    if calibration.build_plate_surface_id is not None:
        base_settings["preferred_build_plate_surface_id"] = calibration.build_plate_surface_id

    validated_settings = MaterialSettingsInput.model_validate(base_settings).model_dump(mode="json")
    profile = MaterialProfile(
        **profile_columns_from_settings(validated_settings),
        filament_product_id=calibration.filament_product_id,
        printer_id=calibration.printer_id,
        nozzle_diameter_mm=calibration.nozzle_diameter_mm,
        version=(latest or 0) + 1,
        status=ProfileStatus.PUBLISHED,
        base_template_revision_id=base_revision.id,
        setting_overrides=sparse_profile_overrides(base_revision.settings, validated_settings),
        ironing_enabled=results.get(
            "ironing_enabled",
            baseline.ironing_enabled if baseline is not None else None,
        ),
        ironing_flow_percent=(
            _decimal_result(results, "ironing_flow_percent")
            if "ironing_flow_percent" in results
            else baseline.ironing_flow_percent
            if baseline is not None
            else None
        ),
        ironing_speed_mm_s=(
            _decimal_result(results, "ironing_speed_mm_s")
            if "ironing_speed_mm_s" in results
            else baseline.ironing_speed_mm_s
            if baseline is not None
            else None
        ),
        ironing_line_spacing_mm=(
            _decimal_result(results, "ironing_line_spacing_mm")
            if "ironing_line_spacing_mm" in results
            else baseline.ironing_line_spacing_mm
            if baseline is not None
            else None
        ),
        published_at=datetime.now(UTC),
    )
    session.add(profile)
    await session.flush()
    calibration.status = CalibrationStatus.PUBLISHED
    calibration.published_profile_id = profile.id
    calibration.override_reason = override_reason
    calibration.completed_at = datetime.now(UTC)
    calibration.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="calibration.publish_profile",
        object_type="calibration_session",
        object_id=calibration.id,
        before={"status": "ready_to_publish"},
        after={"status": "published", "profile_id": str(profile.id), "override": bool(override_reason)},
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="google.profile.publish",
        idempotency_key=f"profile:{profile.id}:google:v1",
        aggregate_type="material_profile",
        aggregate_id=profile.id,
        aggregate_version=1,
        payload={"profile_id": str(profile.id)},
    )
    await session.commit()
    return ProfileResponse.model_validate(profile)
