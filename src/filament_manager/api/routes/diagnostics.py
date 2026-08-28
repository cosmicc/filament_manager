"""Sanitized diagnostics, recovery validation, backups, and safe repair routes."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, PlainTextResponse, Response
from sqlalchemy import select

from filament_manager.models.operations import DiagnosticRun
from filament_manager.services.database_backups import (
    DatabaseBackupError,
    acquire_backup_lock,
    archive_path,
    archive_payload,
    backup_status,
    cancel_pending_restore,
    create_backup_archive,
    get_backup_policy,
    import_backup_stream,
    list_backup_archives,
    pending_restore,
    prepare_restore,
    prune_automatic_archives,
    record_backup_failure,
    release_backup_lock,
    update_backup_policy,
)
from filament_manager.services.diagnostics import (
    diagnostics_text,
    operational_overview,
    queue_projection_rebuild,
    run_recovery_validation,
)
from filament_manager.services.events import add_audit_event
from filament_manager.services.version_status import version_status

from ..dependencies import Administrator, DatabaseSession, Viewer
from ..errors import ApiError
from ..schemas import (
    DatabaseBackupArchiveResponse,
    DatabaseBackupOverviewResponse,
    DatabaseBackupPolicyResponse,
    DatabaseBackupPolicyUpdate,
    DatabaseRestoreRequest,
    DatabaseRestoreRequestResponse,
    DiagnosticOverviewResponse,
    DiagnosticRunResponse,
    ProjectionRebuildResponse,
    VersionStatusResponse,
)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])
logger = structlog.get_logger()


def _backup_api_error(error: DatabaseBackupError, *, status_code: int = 400) -> ApiError:
    """Translate one already-bounded backup failure into a stable API error."""

    return ApiError(status_code, "database_backup_error", str(error))


@router.get("", response_model=DiagnosticOverviewResponse)
async def diagnostics_overview(
    _: Viewer,
    session: DatabaseSession,
) -> DiagnosticOverviewResponse:
    """Return current sanitized connections, workers, syncs, queues, and errors."""

    return DiagnosticOverviewResponse.model_validate(await operational_overview(session))


@router.get("/log.txt", response_class=PlainTextResponse)
async def download_diagnostics_log(
    _: Viewer,
    session: DatabaseSession,
) -> PlainTextResponse:
    """Download the current bounded diagnostic overview as sanitized plain text."""

    overview = await operational_overview(session)
    checked_at = overview["checked_at"]
    assert isinstance(checked_at, datetime)
    filename = f"filament-manager-diagnostics-{checked_at.strftime('%Y%m%dT%H%M%SZ')}.txt"
    return PlainTextResponse(
        diagnostics_text(overview),
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/version", response_model=VersionStatusResponse)
async def application_version_status(_: Viewer) -> VersionStatusResponse:
    """Return the running version and cached latest published GitHub release."""

    return VersionStatusResponse.model_validate(await version_status())


@router.get("/database-backups", response_model=DatabaseBackupOverviewResponse)
async def database_backup_overview(
    _: Viewer,
    session: DatabaseSession,
) -> DatabaseBackupOverviewResponse:
    """Return policy and validated canonical-database archives without file contents."""

    policy = await get_backup_policy(session)
    archives = await asyncio.to_thread(list_backup_archives)
    return DatabaseBackupOverviewResponse.model_validate(
        {
            "policy": policy,
            "status": await asyncio.to_thread(backup_status),
            "pending_restore": await asyncio.to_thread(pending_restore),
            "archives": [archive_payload(archive) for archive in archives],
        }
    )


@router.put("/database-backups/policy", response_model=DatabaseBackupPolicyResponse)
async def save_database_backup_policy(
    payload: DatabaseBackupPolicyUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> DatabaseBackupPolicyResponse:
    """Save the automatic canonical-database backup interval and retention."""

    before = await get_backup_policy(session)
    try:
        policy = await update_backup_policy(
            session,
            enabled=payload.enabled,
            interval_hours=payload.interval_hours,
            retention_count=payload.retention_count,
            expected_version=payload.expected_version,
            updated_by=administrator.id,
        )
    except DatabaseBackupError as error:
        await session.rollback()
        raise _backup_api_error(error, status_code=status.HTTP_409_CONFLICT) from error
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="database.backup.policy.update",
        object_type="application_setting",
        object_id=None,
        before=jsonable_encoder(before),
        after=jsonable_encoder(policy),
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    await asyncio.to_thread(prune_automatic_archives, policy.retention_count)
    return DatabaseBackupPolicyResponse.model_validate(policy)


@router.post(
    "/database-backups",
    response_model=DatabaseBackupArchiveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_database_backup(
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> DatabaseBackupArchiveResponse:
    """Create one downloadable canonical PostgreSQL backup immediately."""

    if not await acquire_backup_lock(session):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "database_backup_busy",
            "Another database backup is already running.",
        )
    try:
        archive = await asyncio.to_thread(create_backup_archive, "manual")
        policy = await get_backup_policy(session)
        await asyncio.to_thread(prune_automatic_archives, policy.retention_count)
    except DatabaseBackupError as error:
        await asyncio.to_thread(record_backup_failure)
        raise _backup_api_error(error) from error
    finally:
        await release_backup_lock(session)
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="database.backup.create",
        object_type="database_backup",
        object_id=archive.id,
        before=None,
        after={"trigger": "manual", "archive_sha256": archive.archive_sha256},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return DatabaseBackupArchiveResponse.model_validate(archive_payload(archive))


@router.post(
    "/database-backups/import",
    response_model=DatabaseBackupArchiveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_database_backup(
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> DatabaseBackupArchiveResponse:
    """Stream and privately stage one trusted downloaded Filament Manager ZIP."""

    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type not in {"application/zip", "application/octet-stream"}:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "database_backup_file_type",
            "Choose a Filament Manager database backup ZIP file.",
        )
    try:
        archive = await import_backup_stream(request.stream())
    except DatabaseBackupError as error:
        raise _backup_api_error(error) from error
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="database.backup.import",
        object_type="database_backup",
        object_id=archive.id,
        before=None,
        after={"archive_sha256": archive.archive_sha256},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return DatabaseBackupArchiveResponse.model_validate(archive_payload(archive))


@router.get("/database-backups/{backup_id}/download")
async def download_database_backup(
    backup_id: UUID,
    _: Viewer,
) -> FileResponse:
    """Download one fully validated private ZIP without exposing its filesystem path."""

    try:
        archive, path = await asyncio.to_thread(archive_path, backup_id)
    except DatabaseBackupError as error:
        raise _backup_api_error(error, status_code=status.HTTP_404_NOT_FOUND) from error
    return FileResponse(
        path,
        media_type="application/zip",
        filename=archive.filename,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/database-backups/{backup_id}/restore-request",
    response_model=DatabaseRestoreRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def prepare_database_restore(
    backup_id: UUID,
    payload: DatabaseRestoreRequest,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> DatabaseRestoreRequestResponse:
    """Stage an exact archive for the dedicated stopped-service restore command."""

    if payload.confirmation != "RESTORE":
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "database_restore_confirmation",
            "Type RESTORE exactly to prepare this destructive database restore.",
        )
    try:
        result = await asyncio.to_thread(
            prepare_restore,
            backup_id,
            requested_by=administrator.id,
        )
    except DatabaseBackupError as error:
        raise _backup_api_error(error, status_code=status.HTTP_409_CONFLICT) from error
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="database.backup.restore.prepare",
        object_type="database_backup",
        object_id=backup_id,
        before=None,
        after={"request_id": str(result["request_id"])},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return DatabaseRestoreRequestResponse.model_validate(result)


@router.delete("/database-backups/restore-request", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_database_restore(
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> Response:
    """Cancel a prepared restore before the offline command begins."""

    removed = await asyncio.to_thread(cancel_pending_restore)
    if removed:
        add_audit_event(
            session,
            actor_id=administrator.id,
            source="web",
            action="database.backup.restore.cancel",
            object_type="database_backup",
            object_id=None,
            before={"status": "pending"},
            after={"status": "cancelled"},
            correlation_id=request.state.correlation_id,
        )
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
