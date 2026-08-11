"""Administrator workbook upload, validation, and commit routes."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4
from zipfile import BadZipFile

from fastapi import APIRouter, File, Request, UploadFile, status
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import select

from filament_manager.config import get_settings
from filament_manager.models.operations import ImportRun
from filament_manager.services.events import add_audit_event
from filament_manager.services.seed import seed_configured_system
from filament_manager.services.workbook_import import analyze_workbook, commit_approved_run

from ..dependencies import Administrator, DatabaseSession
from ..errors import ApiError
from ..schemas import WorkbookImportRunResponse

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_WORKBOOK_UPLOAD_BYTES = 10 * 1024 * 1024
WORKBOOK_IMPORT_DIRECTORY = "workbook-imports"


def _workbook_directory() -> Path:
    directory = get_settings().app.data_dir / WORKBOOK_IMPORT_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _workbook_path(run_id: UUID) -> Path:
    return _workbook_directory() / f"{run_id}.xlsx"


def _upload_source_name(filename: str | None) -> str:
    raw = (filename or "").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1].strip()
    if not name:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "workbook_filename_required",
            "Filename required",
        )
    if "\x00" in name or "/" in name or "\\" in name:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_workbook_filename",
            "Workbook filename is invalid",
        )
    if len(name) > 256:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "workbook_filename_too_long",
            "Workbook filename is too long",
        )
    if not name.casefold().endswith(".xlsx"):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "workbook_file_required",
            "Upload an .xlsx workbook",
        )
    return name


async def _write_uploaded_workbook(upload: UploadFile, destination: Path) -> None:
    temp_path = destination.with_suffix(".uploading")
    total = 0
    try:
        with temp_path.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_WORKBOOK_UPLOAD_BYTES:
                    raise ApiError(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "workbook_too_large",
                        "Workbook uploads are limited to 10 MB",
                    )
                handle.write(chunk)
        if total == 0:
            raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "workbook_empty", "Workbook file is empty")
        temp_path.replace(destination)
    finally:
        temp_path.unlink(missing_ok=True)
        await upload.close()


def _run_response(run: ImportRun) -> WorkbookImportRunResponse:
    return WorkbookImportRunResponse(
        id=run.id,
        source_name=run.source_name,
        source_sha256=run.source_sha256,
        dry_run=run.dry_run,
        status=run.status,
        report=run.report,
        approved_by=run.approved_by,
        created_at=run.created_at,
        completed_at=run.completed_at,
        stored_workbook=_workbook_path(run.id).is_file(),
    )


def _validation_error(exc: Exception) -> ApiError:
    return ApiError(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_workbook",
        str(exc) or "Workbook could not be validated",
    )


@router.get("/workbook", response_model=list[WorkbookImportRunResponse])
async def list_workbook_imports(
    _: Administrator,
    session: DatabaseSession,
    limit: int = 20,
) -> list[WorkbookImportRunResponse]:
    """List recent workbook validation and import runs without exposing server paths."""

    bounded_limit = min(max(limit, 1), 100)
    result = await session.execute(
        select(ImportRun).order_by(ImportRun.created_at.desc()).limit(bounded_limit)
    )
    return [_run_response(run) for run in result.scalars()]


@router.post(
    "/workbook/dry-run",
    response_model=WorkbookImportRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_workbook_dry_run(
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
    file: Annotated[UploadFile, File()],
) -> WorkbookImportRunResponse:
    """Upload one workbook, validate it, and persist a hash-bound dry-run report."""

    source_name = _upload_source_name(file.filename)
    run_id = uuid4()
    destination = _workbook_path(run_id)
    try:
        await _write_uploaded_workbook(file, destination)
        report = analyze_workbook(destination, source_name=source_name)
    except ApiError:
        destination.unlink(missing_ok=True)
        raise
    except (BadZipFile, InvalidFileException, ValueError) as exc:
        destination.unlink(missing_ok=True)
        raise _validation_error(exc) from exc

    completed_at = datetime.now(UTC)
    run = ImportRun(
        id=run_id,
        source_name=source_name,
        source_sha256=str(report["sha256"]),
        dry_run=True,
        status="validated" if report["invalid_rows"] == 0 else "invalid",
        report=report,
        created_at=completed_at,
        completed_at=completed_at,
    )
    session.add(run)
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="workbook.import.validate",
        object_type="import_run",
        object_id=run.id,
        before=None,
        after={
            "status": run.status,
            "source_name": source_name,
            "valid_rows": int(report["valid_rows"]),
            "invalid_rows": int(report["invalid_rows"]),
        },
        correlation_id=request.state.correlation_id,
    )
    try:
        await session.commit()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return _run_response(run)


@router.post("/workbook/{run_id}/commit")
async def commit_workbook_import(
    run_id: UUID,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> dict[str, int]:
    """Commit a validated uploaded workbook into the canonical database."""

    workbook_path = _workbook_path(run_id)
    if not workbook_path.is_file():
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "uploaded_workbook_missing",
            "The validated uploaded workbook is no longer available",
        )
    seeded = await seed_configured_system(session, get_settings())
    if seeded["plates"] or seeded["printers"]:
        add_audit_event(
            session,
            actor_id=administrator.id,
            source="web",
            action="system.seed.auto",
            object_type="system",
            object_id=None,
            before=None,
            after={"plates": seeded["plates"], "printers": seeded["printers"]},
            correlation_id=request.state.correlation_id,
        )
    try:
        return await commit_approved_run(
            session,
            run_id=run_id,
            workbook_path=workbook_path,
            administrator_username=administrator.username,
            audit_source="web",
            correlation_id=request.state.correlation_id,
        )
    except ValueError as exc:
        message = str(exc)
        code = "workbook_import_rejected"
        status_code = status.HTTP_409_CONFLICT
        if "not found" in message:
            code = "import_run_not_found"
            status_code = status.HTTP_404_NOT_FOUND
        raise ApiError(status_code, code, message) from exc
