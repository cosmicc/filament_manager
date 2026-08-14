"""Canonical print history, G-code inspection, and quality-assessment routes."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from filament_manager.models.enums import PrintJobStatus
from filament_manager.models.printing import PrintAssessment, PrintJob
from filament_manager.services.events import add_audit_event
from filament_manager.services.print_history import profile_success_statistics

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import PrintAssessmentCreate, PrintAssessmentResponse, PrintJobResponse

router = APIRouter(prefix="/prints", tags=["print history"])


def _print_query() -> Select[tuple[PrintJob]]:
    return select(PrintJob).options(selectinload(PrintJob.segments), selectinload(PrintJob.assessments))


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
    return [PrintJobResponse.model_validate(job) for job in result.scalars().unique()]


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
    return PrintJobResponse.model_validate(job)


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
