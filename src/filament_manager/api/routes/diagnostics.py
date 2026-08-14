"""Sanitized diagnostics, recovery validation, and safe repair routes."""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from filament_manager.models.operations import DiagnosticRun
from filament_manager.services.diagnostics import (
    operational_overview,
    queue_projection_rebuild,
    run_recovery_validation,
)
from filament_manager.services.version_status import version_status

from ..dependencies import Administrator, DatabaseSession, Viewer
from ..schemas import (
    DiagnosticOverviewResponse,
    DiagnosticRunResponse,
    ProjectionRebuildResponse,
    VersionStatusResponse,
)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])
logger = structlog.get_logger()


@router.get("", response_model=DiagnosticOverviewResponse)
async def diagnostics_overview(
    _: Viewer,
    session: DatabaseSession,
) -> DiagnosticOverviewResponse:
    """Return current sanitized connections, workers, syncs, queues, and errors."""

    return DiagnosticOverviewResponse.model_validate(await operational_overview(session))


@router.get("/version", response_model=VersionStatusResponse)
async def application_version_status(_: Viewer) -> VersionStatusResponse:
    """Return the running version and cached latest published GitHub release."""

    return VersionStatusResponse.model_validate(await version_status())


@router.get("/validation-runs", response_model=list[DiagnosticRunResponse])
async def list_validation_runs(
    _: Viewer,
    session: DatabaseSession,
) -> list[DiagnosticRunResponse]:
    """Return recent immutable recovery-validation results."""

    runs = await session.scalars(select(DiagnosticRun).order_by(DiagnosticRun.started_at.desc()).limit(25))
    return [DiagnosticRunResponse.model_validate(run) for run in runs]


@router.post(
    "/validation-runs",
    response_model=DiagnosticRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_validation_run(
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> DiagnosticRunResponse:
    """Run and retain non-destructive database and recovery-readiness validation."""

    started_at = datetime.now(UTC)
    run = DiagnosticRun(
        run_type="recovery_validation",
        status="running",
        requested_by=administrator.id,
        results={},
        started_at=started_at,
    )
    session.add(run)
    await session.commit()
    try:
        results = await run_recovery_validation(session)
        run.status = "completed"
        run.results = jsonable_encoder(results)
    except Exception as exc:
        await session.rollback()
        logger.exception(
            "recovery_validation_failed",
            run_id=str(run.id),
            correlation_id=request.state.correlation_id,
            error_class=type(exc).__name__,
        )
        failed_run = await session.get(DiagnosticRun, run.id)
        assert failed_run is not None
        run = failed_run
        run.status = "failed"
        run.results = {
            "summary": {"healthy": 0, "warning": 0, "error": 1, "disabled": 0},
            "checks": [],
            "error": "Recovery validation could not complete; review the error log",
        }
    run.completed_at = datetime.now(UTC)
    await session.commit()
    return DiagnosticRunResponse.model_validate(run)


@router.post("/projection-rebuild", response_model=ProjectionRebuildResponse)
async def rebuild_external_projections(
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> ProjectionRebuildResponse:
    """Queue reconstruction of supported projections without changing canonical data."""

    result = await queue_projection_rebuild(
        session,
        actor_id=administrator.id,
        correlation_id=request.state.correlation_id,
    )
    return ProjectionRebuildResponse.model_validate(result)
