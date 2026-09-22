"""Canonical print history, G-code inspection, and quality-assessment routes."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, select
from sqlalchemy.orm import defer, selectinload

from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.config import get_settings
from filament_manager.domain.gcode_inspection import extract_gcode_metadata
from filament_manager.models.enums import PrintJobStatus
from filament_manager.models.inventory import Printer
from filament_manager.models.printing import PrintAssessment, PrintGcodeArchive, PrintJob
from filament_manager.services.events import add_audit_event
from filament_manager.services.print_activity import ActivityKind, print_activity_dates
from filament_manager.services.print_costs import print_cost_summary, segment_cost
from filament_manager.services.print_gcode import GCODE_PAGE_BYTES, archive_bytes
from filament_manager.services.print_history import profile_success_statistics
from filament_manager.services.print_setting_evidence import retained_setting_summary
from filament_manager.services.print_template_comparison import current_print_template_comparison
from filament_manager.services.printer_connections import configured_printers

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    CloseStalePrintRequest,
    PrintAssessmentCreate,
    PrintAssessmentResponse,
    PrintJobPageResponse,
    PrintJobResponse,
    PrintJobSummaryResponse,
    PrintMaterialSegmentResponse,
)

router = APIRouter(prefix="/prints", tags=["print history"])


@router.get("/activity/{kind}")
async def activity_dates(
    kind: ActivityKind, _: Viewer, session: DatabaseSession
) -> dict[UUID, dict[str, datetime | None]]:
    """Share one cached catalog request across detail displays without printer traffic."""
    return await print_activity_dates(session, kind)


MOONRAKER_HISTORY_STATUSES = frozenset(
    {
        "in_progress",
        "completed",
        "cancelled",
        "error",
        "klippy_shutdown",
        "klippy_disconnect",
        "interrupted",
    }
)
PRINT_PAGE_SIZES: tuple[Literal[10, 25, 50, 100], ...] = (10, 25, 50, 100)


def _print_query(*, include_settings: bool = True) -> Select[tuple[PrintJob]]:
    """Build a print query, deferring large settings archives for list views."""

    query = select(PrintJob).options(
        selectinload(PrintJob.segments),
        selectinload(PrintJob.assessments),
    )
    if not include_settings:
        query = query.options(defer(PrintJob.print_settings_snapshot))
    return query


def _print_response[PrintResponse: PrintJobSummaryResponse](
    job: PrintJob,
    response_type: type[PrintResponse],
) -> PrintResponse:
    """Expose authenticated media links and immutable derived print costs."""

    response = response_type.model_validate(job)
    segments: list[PrintMaterialSegmentResponse] = []
    for segment in job.segments:
        rendered_segment = PrintMaterialSegmentResponse.model_validate(segment)
        cost = segment_cost(segment)
        segments.append(
            rendered_segment.model_copy(
                update={
                    "cost_per_gram": cost[0] if cost else None,
                    "actual_filament_cost": cost[1] if cost else None,
                    "cost_currency": cost[2] if cost else None,
                }
            )
        )
    costs = print_cost_summary(job)
    raw_moonraker_status = job.state_snapshot.get("moonraker_history_status")
    moonraker_status = (
        raw_moonraker_status
        if isinstance(raw_moonraker_status, str) and raw_moonraker_status in MOONRAKER_HISTORY_STATUSES
        else None
    )
    return response.model_copy(
        update={
            **retained_setting_summary(job),
            "moonraker_status": moonraker_status,
            "timelapse_url": f"/api/v1/prints/{job.id}/timelapse" if job.timelapse_url else None,
            "thumbnail_url": (
                f"/api/v1/prints/{job.id}/thumbnail" if job.thumbnail_data is not None else None
            ),
            "segments": segments,
            **costs,
        }
    )


@router.get("", response_model=list[PrintJobSummaryResponse])
async def list_prints(
    _: Viewer,
    session: DatabaseSession,
    print_status: PrintJobStatus | None = None,
    printer_id: UUID | None = None,
    profile_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PrintJobSummaryResponse]:
    """Return bounded newest-first canonical print summaries."""

    query = _print_query(include_settings=False).order_by(
        PrintJob.started_at.desc().nullslast(), PrintJob.created_at.desc()
    )
    if print_status is not None:
        query = query.where(PrintJob.status == print_status)
    if printer_id is not None:
        query = query.where(PrintJob.printer_id == printer_id)
    if profile_id is not None:
        query = query.where(PrintJob.material_profile_id == profile_id)
    query = query.offset(min(max(offset, 0), 100_000)).limit(min(max(limit, 1), 250))
    result = await session.execute(query)
    return [_print_response(job, PrintJobSummaryResponse) for job in result.scalars().unique()]


@router.get("/page", response_model=PrintJobPageResponse)
async def list_print_page(
    _: Viewer,
    session: DatabaseSession,
    print_status: PrintJobStatus | None = None,
    printer_id: UUID | None = None,
    profile_id: UUID | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    per_page: Annotated[int, Query(ge=10, le=100)] = 10,
) -> PrintJobPageResponse:
    """Return one bounded page plus the exact filtered record count."""

    if per_page not in PRINT_PAGE_SIZES:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unsupported_print_page_size",
            "Print page size must be 10, 25, 50, or 100",
        )
    page_size = per_page

    filters = []
    if print_status is not None:
        filters.append(PrintJob.status == print_status)
    if printer_id is not None:
        filters.append(PrintJob.printer_id == printer_id)
    if profile_id is not None:
        filters.append(PrintJob.material_profile_id == profile_id)
    total_items = int(await session.scalar(select(func.count(PrintJob.id)).where(*filters)) or 0)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    effective_page = min(page, total_pages)
    query = (
        _print_query(include_settings=False)
        .where(*filters)
        .order_by(PrintJob.started_at.desc().nullslast(), PrintJob.created_at.desc())
        .offset((effective_page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(query)
    return PrintJobPageResponse(
        items=[_print_response(job, PrintJobSummaryResponse) for job in result.scalars().unique()],
        page=effective_page,
        per_page=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )


@router.get("/profile-statistics")
async def profile_statistics(
    _: Viewer,
    session: DatabaseSession,
    profile_id: Annotated[list[UUID] | None, Query()] = None,
) -> dict[str, dict[str, object]]:
    """Return success distribution for up to four visually compared profiles."""

    unique_ids = list(dict.fromkeys(profile_id or []))
    if len(unique_ids) > 4:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "profile_comparison_limit",
            "Compare no more than four profile versions at once",
        )
    statistics = await profile_success_statistics(session, unique_ids)
    return {str(key): value for key, value in statistics.items()}


@router.get("/{print_id}", response_model=PrintJobResponse)
async def get_print(print_id: UUID, _: Viewer, session: DatabaseSession) -> PrintJobResponse:
    """Return one print with immutable state, segments, inspection, and ratings."""

    job = await session.scalar(_print_query().where(PrintJob.id == print_id))
    if job is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_print", "Print not found")
    response = _print_response(job, PrintJobResponse)
    response.gcode_saved = (
        await session.scalar(
            select(PrintGcodeArchive.print_job_id).where(PrintGcodeArchive.print_job_id == job.id)
        )
    ) is not None
    if not response.cura_quality_profile:
        cura = job.print_settings_snapshot.get("cura")
        global_scope = cura.get("global") if isinstance(cura, dict) else None
        name = global_scope.get("name") if isinstance(global_scope, dict) else None
        if isinstance(name, str) and name.strip() and len(name) <= 255:
            response.cura_quality_profile = name
    response.current_template_comparison = await current_print_template_comparison(
        session, job.print_settings_snapshot
    )
    return response


async def _idle_history_client(session: DatabaseSession, job: PrintJob) -> MoonrakerClient:
    """Fail closed on unavailable/active printers; never send a motion command."""
    printer = await session.get(Printer, job.printer_id)
    configured = next(
        (
            item
            for item in await configured_printers(session, get_settings())
            if printer is not None and item.id == printer.printer_code
        ),
        None,
    )
    if configured is None:
        raise ApiError(409, "printer_unavailable", "Connect this printer to verify its idle state first")
    client = MoonrakerClient(configured)
    try:
        live = await client.print_state()
    except MoonrakerError as error:
        raise ApiError(409, "printer_unavailable", "Printer state could not be verified") from error
    if live.state not in {"standby", "complete", "cancelled", "error"}:
        raise ApiError(409, "printer_busy", "This action requires a verified idle printer")
    return client


@router.post("/{print_id}/close-stale")
async def close_stale_print(
    print_id: UUID,
    payload: CloseStalePrintRequest,
    actor: Operator,
    session: DatabaseSession,
    request: Request,
) -> dict[str, str]:
    """Close only local unresolved history; leave outcome, end time and usage unknown."""
    job = await session.scalar(select(PrintJob).where(PrintJob.id == print_id).with_for_update())
    if job is None:
        raise ApiError(404, "unknown_print", "Print not found")
    if job.record_version != payload.expected_version or job.status != PrintJobStatus.IN_PROGRESS:
        raise ApiError(409, "print_changed", "Print changed; reload its details")
    await _idle_history_client(session, job)
    before: dict[str, object] = {"status": job.status.value}
    job.status = PrintJobStatus.LEGACY_UNKNOWN
    job.state_snapshot = {
        **job.state_snapshot,
        "moonraker_history_status": "interrupted",
        "stale_closed_at": datetime.now(UTC).isoformat(),
    }
    job.record_version += 1
    add_audit_event(
        session,
        actor_id=actor.id,
        source="web",
        action="print.history.close_stale",
        object_type="print_job",
        object_id=job.id,
        before=before,
        after={"status": "interrupted_outcome_unknown"},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"status": "interrupted_outcome_unknown"}


@router.post("/{print_id}/gcode/capture")
async def capture_verified_print_gcode(
    print_id: UUID,
    _: Operator,
    session: DatabaseSession,
) -> dict[str, bool]:
    """Backfill only an original matching its immutable inspection digest, while idle."""
    job = await session.scalar(select(PrintJob).where(PrintJob.id == print_id).with_for_update())
    if job is None:
        raise ApiError(404, "unknown_print", "Print not found")
    if await session.get(PrintGcodeArchive, print_id) is not None:
        return {"saved": True}
    if not job.gcode_sha256:
        raise ApiError(
            409,
            "gcode_unverifiable",
            "This older print has no original checksum; its file cannot be verified",
        )
    client = await _idle_history_client(session, job)
    try:
        original = await client.gcode_file(job.filename, max_bytes=100_000_000)
    except (MoonrakerError, ValueError) as error:
        raise ApiError(
            409, "gcode_unavailable", "The original file is unavailable or exceeds 100 MB"
        ) from error
    if original.sha256 != job.gcode_sha256 or original.compressed_data is None:
        raise ApiError(
            409, "gcode_changed", "The printer file no longer matches this print's original checksum"
        )
    session.add(
        PrintGcodeArchive(
            print_job_id=job.id,
            sha256=original.sha256,
            size_bytes=original.size,
            compressed_data=original.compressed_data,
        )
    )
    if not job.cura_quality_profile:
        name = extract_gcode_metadata({}, original.header, original.tail).get("cura_quality_profile")
        if isinstance(name, str):
            job.cura_quality_profile = name
            job.record_version += 1
    await session.commit()
    return {"saved": True}


@router.get("/{print_id}/gcode")
async def get_print_gcode(
    print_id: UUID,
    _: Viewer,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1, le=4000)] = 1,
    download: bool = False,
) -> Response:
    """Serve only authenticated stored originals, with bounded inert text pages."""
    archive = await session.get(PrintGcodeArchive, print_id)
    if archive is None:
        raise ApiError(404, "gcode_unavailable", "No verified G-code copy was saved for this print")
    try:
        data = archive_bytes(archive)
    except ValueError as error:
        raise ApiError(409, "gcode_invalid", "The saved G-code failed integrity validation") from error
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
    if download:
        filename = await session.scalar(select(PrintJob.filename).where(PrintJob.id == print_id))
        leaf = (filename or f"print-{print_id}.gcode").replace("\\", "/").rsplit("/", 1)[-1]
        headers["Content-Disposition"] = (
            f"attachment; filename=\"print-{print_id}.gcode\"; filename*=UTF-8''{quote(leaf, safe='')}"
        )
        return Response(data, media_type="application/octet-stream", headers=headers)
    from fastapi.responses import JSONResponse

    total_pages = max(1, (len(data) + GCODE_PAGE_BYTES - 1) // GCODE_PAGE_BYTES)
    effective_page = min(page, total_pages)
    offset = (effective_page - 1) * GCODE_PAGE_BYTES
    return JSONResponse(
        {
            "text": data[offset : offset + GCODE_PAGE_BYTES].decode("utf-8", errors="replace"),
            "page": effective_page,
            "total_pages": total_pages,
            "size_bytes": archive.size_bytes,
            "sha256": archive.sha256,
        },
        headers=headers,
    )


@router.get("/{print_id}/thumbnail")
async def get_print_thumbnail(
    print_id: UUID,
    request: Request,
    _: Viewer,
    session: DatabaseSession,
) -> Response:
    """Return one sanitized stored thumbnail without exposing Moonraker."""

    job = await session.get(PrintJob, print_id)
    if (
        job is None
        or job.thumbnail_data is None
        or job.thumbnail_media_type is None
        or job.thumbnail_sha256 is None
    ):
        raise ApiError(status.HTTP_404_NOT_FOUND, "thumbnail_unknown", "Thumbnail not found")
    etag = f'"{job.thumbnail_sha256}"'
    headers = {
        "Cache-Control": "private, max-age=86400",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=job.thumbnail_data, media_type=job.thumbnail_media_type, headers=headers)


@router.get("/{print_id}/timelapse")
async def stream_print_timelapse(
    print_id: UUID,
    request: Request,
    _: Viewer,
    session: DatabaseSession,
) -> StreamingResponse:
    """Stream one associated MP4 through the authenticated application boundary."""

    job = await session.get(PrintJob, print_id)
    if job is None or job.timelapse_url is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "timelapse_unknown", "Timelapse not found")
    printer = await session.get(Printer, job.printer_id)
    configured = next(
        (
            item
            for item in (await configured_printers(session, get_settings()))
            if printer is not None and item.id == printer.printer_code
        ),
        None,
    )
    if configured is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "timelapse_unknown", "Timelapse not found")
    try:
        filename = MoonrakerClient.validated_timelapse_filename(job.timelapse_url)
    except ValueError as error:
        raise ApiError(status.HTTP_404_NOT_FOUND, "timelapse_unknown", "Timelapse not found") from error
    range_header = request.headers.get("range")
    if range_header is not None and (
        len(range_header) > 80
        or not range_header.startswith("bytes=")
        or any(ord(char) < 32 for char in range_header)
    ):
        raise ApiError(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "invalid_range", "Invalid video range"
        )
    api_key = configured.resolved_api_key()
    upstream_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30, read=None),
        headers={"X-Api-Key": api_key} if api_key is not None else {},
    )
    headers = {"Range": range_header} if range_header is not None else {}
    try:
        upstream = await upstream_client.send(
            upstream_client.build_request(
                "GET",
                f"{str(configured.base_url).rstrip('/')}/server/files/timelapse/{quote(filename, safe='/')}",
                headers=headers,
            ),
            stream=True,
        )
    except httpx.HTTPError as error:
        await upstream_client.aclose()
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY, "timelapse_unavailable", "Timelapse is unavailable"
        ) from error
    if upstream.status_code not in {status.HTTP_200_OK, status.HTTP_206_PARTIAL_CONTENT}:
        await upstream.aclose()
        await upstream_client.aclose()
        raise ApiError(status.HTTP_404_NOT_FOUND, "timelapse_unknown", "Timelapse not found")

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await upstream_client.aclose()

    safe_headers = {"Accept-Ranges": "bytes", "Content-Disposition": "inline"}
    for header in ("content-length", "content-range"):
        if value := upstream.headers.get(header):
            safe_headers[header.title()] = value
    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        media_type="video/mp4",
        headers=safe_headers,
    )


@router.post(
    "/{print_id}/assessments",
    response_model=PrintAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assess_print(
    print_id: UUID,
    payload: PrintAssessmentCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> PrintAssessmentResponse:
    """Append a quality revision without overwriting an earlier assessment."""

    job = await session.scalar(select(PrintJob).where(PrintJob.id == print_id).with_for_update())
    if job is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_print", "Print not found")
    if job.status == PrintJobStatus.IN_PROGRESS:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "print_in_progress",
            "Assess the print after Moonraker reports that it has finished",
        )
    previous = await session.scalar(
        select(PrintAssessment)
        .where(PrintAssessment.print_job_id == print_id)
        .order_by(PrintAssessment.revision.desc())
        .limit(1)
    )
    assessment = PrintAssessment(
        print_job_id=print_id,
        revision=(previous.revision + 1) if previous else 1,
        rating=payload.rating,
        defect_tags=payload.defect_tags,
        notes=payload.notes.strip() if payload.notes else None,
        assessed_by=operator.id,
        supersedes_id=previous.id if previous else None,
        created_at=datetime.now(UTC),
    )
    session.add(assessment)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="print.assessment.create",
        object_type="print_assessment",
        object_id=assessment.id,
        before={"supersedes_id": str(previous.id)} if previous else None,
        after={
            "print_job_id": str(print_id),
            "revision": assessment.revision,
            "rating": assessment.rating.value,
            "defect_tags": assessment.defect_tags,
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return PrintAssessmentResponse.model_validate(assessment)
