"""Resumable six-step calibration workflow routes."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from filament_manager.domain.calibration import CALIBRATION_STEPS, invalidated_statuses, ready_to_publish
from filament_manager.models.calibration import CalibrationSession, CalibrationStep
from filament_manager.models.enums import CalibrationStatus, CalibrationStepStatus, ProfileStatus
from filament_manager.models.inventory import FilamentProduct, MaterialProfile, Printer
from filament_manager.services.events import add_audit_event, add_outbox_job

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    CalibrationCreate,
    CalibrationResponse,
    CalibrationStepUpdate,
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
    """Start a calibration session with the exact six supplied steps."""

    if await session.get(FilamentProduct, payload.filament_product_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_filament", "Filament not found")
    if await session.get(Printer, payload.printer_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_printer", "Printer not found")
    calibration = CalibrationSession(
        **payload.model_dump(),
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
    """Return a resumable session and all six steps."""

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
    step.result = payload.result
    step.artifact = payload.artifact
    step.notes = payload.notes
    if payload.complete:
        if not payload.result:
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
    profile = MaterialProfile(
        filament_product_id=calibration.filament_product_id,
        printer_id=calibration.printer_id,
        nozzle_diameter_mm=calibration.nozzle_diameter_mm,
        version=(latest or 0) + 1,
        status=ProfileStatus.PUBLISHED,
        chamber_temp_c=_decimal_result(results, "chamber_temp_c"),
        extruder_temp_c=_decimal_result(results, "extruder_temp_c", Decimal("0")),
        bed_temp_c=_decimal_result(results, "bed_temp_c", Decimal("0")),
        flow_percent=_decimal_result(results, "flow_percent", Decimal("100")),
        retraction_distance_mm=_decimal_result(results, "retraction_distance_mm"),
        retraction_speed_mm_s=_decimal_result(results, "retraction_speed_mm_s"),
        cooling_enabled=bool(results.get("cooling_enabled", True)),
        cooling_min_percent=_decimal_result(results, "cooling_min_percent", Decimal("0")),
        cooling_max_percent=_decimal_result(results, "cooling_max_percent", Decimal("100")),
        support_overhang_angle_deg=_decimal_result(results, "support_overhang_angle_deg"),
        tree_max_branch_angle_deg=_decimal_result(results, "tree_max_branch_angle_deg"),
        pressure_advance=_decimal_result(results, "pressure_advance"),
        filament_density_g_cm3=product.density_g_cm3,
        preferred_build_plate_id=calibration.build_plate_id,
        ironing_enabled=results.get("ironing_enabled"),
        ironing_flow_percent=_decimal_result(results, "ironing_flow_percent"),
        ironing_speed_mm_s=_decimal_result(results, "ironing_speed_mm_s"),
        ironing_line_spacing_mm=_decimal_result(results, "ironing_line_spacing_mm"),
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
