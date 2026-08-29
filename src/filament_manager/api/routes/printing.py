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
from sqlalchemy.orm import selectinload

from filament_manager.clients.moonraker import MoonrakerClient
from filament_manager.config import get_settings
from filament_manager.models.enums import PrintJobStatus
from filament_manager.models.inventory import Printer
from filament_manager.models.printing import PrintAssessment, PrintJob
from filament_manager.services.events import add_audit_event
from filament_manager.services.print_costs import print_cost_summary, segment_cost
from filament_manager.services.print_history import profile_success_statistics

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    PrintAssessmentCreate,
    PrintAssessmentResponse,
    PrintJobPageResponse,
    PrintJobResponse,
    PrintMaterialSegmentResponse,
)

router = APIRouter(prefix="/prints", tags=["print history"])

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


def _print_query() -> Select[tuple[PrintJob]]:
    return select(PrintJob).options(selectinload(PrintJob.segments), selectinload(PrintJob.assessments))


def _print_response(job: PrintJob) -> PrintJobResponse:
    """Expose authenticated media links and immutable derived print costs."""

    response = PrintJobResponse.model_validate(job)
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
            "moonraker_status": moonraker_status,
            "timelapse_url": f"/api/v1/prints/{job.id}/timelapse" if job.timelapse_url else None,
            "thumbnail_url": (
                f"/api/v1/prints/{job.id}/thumbnail" if job.thumbnail_data is not None else None
            ),
            "segments": segments,
            **costs,
        }
    )


@router.get("", response_model=list[PrintJobResponse])
async def list_prints(
    _: Viewer,
    session: DatabaseSession,
    print_status: PrintJobStatus | None = None,
    profile_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PrintJobResponse]:
    """Return bounded newest-first canonical print records and exact snapshots."""

    query = _print_query().order_by(PrintJob.started_at.desc().nullslast(), PrintJob.created_at.desc())
    if print_status is not None:
        query = query.where(PrintJob.status == print_status)
    if profile_id is not None:
        query = query.where(PrintJob.material_profile_id == profile_id)
    query = query.offset(min(max(offset, 0), 100_000)).limit(min(max(limit, 1), 250))
    result = await session.execute(query)
    return [_print_response(job) for job in result.scalars().unique()]


@router.get("/page", response_model=PrintJobPageResponse)
async def list_print_page(
    _: Viewer,
    session: DatabaseSession,
    print_status: PrintJobStatus | None = None,
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
    if profile_id is not None:
        filters.append(PrintJob.material_profile_id == profile_id)
    total_items = int(await session.scalar(select(func.count(PrintJob.id)).where(*filters)) or 0)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    effective_page = min(page, total_pages)
    query = (
        _print_query()
        .where(*filters)
        .order_by(PrintJob.started_at.desc().nullslast(), PrintJob.created_at.desc())
        .offset((effective_page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(query)
    return PrintJobPageResponse(
        items=[_print_response(job) for job in result.scalars().unique()],
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
    return _print_response(job)


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
            for item in get_settings().moonraker.printers
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
