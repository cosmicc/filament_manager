"""Authenticated per-template plate-side ratings and ordered recommendations."""

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, StrictInt, field_validator
from sqlalchemy import select

from filament_manager.models.inventory import BuildPlateSurface, MaterialTemplate, Printer
from filament_manager.models.operations import ApplicationSetting
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.plate_ratings import RATING_PREFIX, filament_template_id, template_ratings

from ..dependencies import Administrator, DatabaseSession, Viewer
from ..errors import ApiError

router = APIRouter(prefix="/build-plate-ratings", tags=["build plate compatibility"])


class RatingUpdate(BaseModel):
    """Complete bounded rating map; omitted sides remain unrated."""

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
    query = select(Printer)
    if printer_id is not None:
        query = query.where(Printer.id == printer_id)
    result = []
    for printer in await session.scalars(query):
        template_id = await filament_template_id(session, printer, filament_id)
        if template_id is not None:
            result.append(
                {
                    **await template_ratings(session, template_id),
                    "printer_id": str(printer.id),
                    "printer_name": printer.name,
                    "active_side_id": str(printer.active_plate_surface_id)
                    if printer.active_plate_surface_id
                    else None,
                }
            )
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
    known = set(
        await session.scalars(select(BuildPlateSurface.id).where(BuildPlateSurface.id.in_(payload.ratings)))
    )
    if known != set(payload.ratings):
        raise ApiError(422, "unknown_plate_side", "Choose existing build plate sides")
    key = f"{RATING_PREFIX}{template_id}"
    setting = await session.scalar(
        select(ApplicationSetting).where(ApplicationSetting.key == key).with_for_update()
    )
    if payload.expected_version != (setting.record_version if setting else 0):
        raise ApiError(409, "record_version_conflict", "Ratings changed; reload before saving")
    before = dict(setting.value) if setting else {}
    if setting is None:
        setting = ApplicationSetting(key=key, value={}, record_version=0)
        session.add(setting)
    setting.value = {str(side): stars for side, stars in payload.ratings.items()}
    setting.record_version += 1
    setting.updated_by = administrator.id
    add_outbox_job(
        session,
        job_type="google.profile.publish",
        idempotency_key=f"plate-ratings:{template_id}:v{setting.record_version}",
        aggregate_type="material_template",
        aggregate_id=template_id,
        aggregate_version=setting.record_version,
        payload={"template_id": str(template_id)},
    )
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="template.plate_ratings.update",
        object_type="material_template",
        object_id=template_id,
        before=before,
        after=setting.value,
        correlation_id=request.state.correlation_id,
    )
    await session.flush()
    result = await template_ratings(session, template_id)
    await session.commit()
    return result
