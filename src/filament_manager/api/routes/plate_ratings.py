"""Authenticated whole-plate template ratings and sparse filament overrides."""

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, StrictInt, field_validator
from sqlalchemy import select

from filament_manager.models.inventory import BuildPlate, FilamentProduct, MaterialTemplate, Printer
from filament_manager.models.operations import ApplicationSetting
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.plate_ratings import (
    OVERRIDE_PREFIX,
    RATING_PREFIX,
    effective_ratings,
    filament_overrides,
    template_ratings,
)

from ..dependencies import Administrator, DatabaseSession, Viewer
from ..errors import ApiError

router = APIRouter(prefix="/build-plate-ratings", tags=["build plate compatibility"])


class RatingUpdate(BaseModel):
    """Complete bounded map; omitted plates remain unrated or inherit."""

    expected_version: int = Field(ge=0)
    ratings: dict[UUID, StrictInt] = Field(max_length=1000)

    @field_validator("ratings")
    @classmethod
    def valid_stars(cls, values: dict[UUID, int]) -> dict[UUID, int]:
        """Keep explicit avoidance distinct from absent/unrated entries."""
        if any(value < 0 or value > 5 for value in values.values()):
            raise ValueError("Ratings must be between zero and five stars")
        return values


@router.get("/filament/{filament_id}")
async def compatibility(
    filament_id: UUID, _: Viewer, session: DatabaseSession, printer_id: UUID | None = None
) -> list[dict[str, object]]:
    """Return compatibility per current printer scope without printer traffic."""
    if await session.get(FilamentProduct, filament_id) is None:
        raise ApiError(404, "unknown_filament", "Filament not found")
    query = select(Printer)
    if printer_id is not None:
        query = query.where(Printer.id == printer_id)
    result = []
    for printer in await session.scalars(query):
        result.append(await effective_ratings(session, printer, filament_id))
    return result


@router.get("/filament/{filament_id}/overrides")
async def get_overrides(filament_id: UUID, _: Viewer, session: DatabaseSession) -> dict[str, object]:
    """Return explicit ownership separately from current inherited defaults."""
    if await session.get(FilamentProduct, filament_id) is None:
        raise ApiError(404, "unknown_filament", "Filament not found")
    return await filament_overrides(session, filament_id)


@router.put("/filament/{filament_id}/overrides")
async def save_overrides(
    filament_id: UUID,
    payload: RatingUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> dict[str, object]:
    """Serialize first creation and keep overrides with the physical filament."""
    filament = await session.scalar(
        select(FilamentProduct).where(FilamentProduct.id == filament_id).with_for_update()
    )
    if filament is None or filament.archived:
        raise ApiError(404, "unknown_filament", "Active filament not found")
    await _write_ratings(
        session,
        payload,
        request,
        administrator,
        filament_id,
        OVERRIDE_PREFIX,
        "filament_product",
        "filament.plate_ratings.update",
    )
    result = await filament_overrides(session, filament_id)
    await session.commit()
    return result


@router.get("/{template_id}")
async def get_ratings(template_id: UUID, _: Viewer, session: DatabaseSession) -> dict[str, object]:
    """Read an existing template's ratings without creating a settings record."""
    if await session.get(MaterialTemplate, template_id) is None:
        raise ApiError(404, "unknown_template", "Material template not found")
    return await template_ratings(session, template_id)


@router.put("/{template_id}")
async def save_ratings(
    template_id: UUID,
    payload: RatingUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> dict[str, object]:
    """Serialize creation with the template lock and audit every rating change."""
    template = await session.scalar(
        select(MaterialTemplate).where(MaterialTemplate.id == template_id).with_for_update()
    )
    if template is None or not template.active:
        raise ApiError(404, "unknown_template", "Active material template not found")
    await _write_ratings(
        session,
        payload,
        request,
        administrator,
        template_id,
        RATING_PREFIX,
        "material_template",
        "template.plate_ratings.update",
    )
    result = await template_ratings(session, template_id)
    await session.commit()
    return result


async def _write_ratings(
    session: DatabaseSession,
    payload: RatingUpdate,
    request: Request,
    administrator: Administrator,
    identity: UUID,
    prefix: str,
    object_type: str,
    action: str,
) -> None:
    """Write after the owner lock; audit and publication are transaction-atomic."""
    known = set(await session.scalars(select(BuildPlate.id).where(BuildPlate.id.in_(payload.ratings))))
    if known != set(payload.ratings):
        raise ApiError(422, "unknown_build_plate", "Choose existing whole build plates")
    key = f"{prefix}{identity}"
    setting = await session.scalar(
        select(ApplicationSetting).where(ApplicationSetting.key == key).with_for_update()
    )
    if payload.expected_version != (setting.record_version if setting else 0):
        raise ApiError(409, "record_version_conflict", "Ratings changed; reload before saving")
    before = dict(setting.value) if setting else {}
    if setting is None:
        setting = ApplicationSetting(key=key, value={}, record_version=0)
        session.add(setting)
    setting.value = {str(plate): stars for plate, stars in payload.ratings.items()}
    setting.record_version += 1
    setting.updated_by = administrator.id
    add_outbox_job(
        session,
        job_type="google.profile.publish",
        idempotency_key=f"{prefix}{identity}:v{setting.record_version}",
        aggregate_type=object_type,
        aggregate_id=identity,
        aggregate_version=setting.record_version,
        payload={"object_id": str(identity)},
    )
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action=action,
        object_type=object_type,
        object_id=identity,
        before=before,
        after=setting.value,
        correlation_id=request.state.correlation_id,
    )
    await session.flush()
