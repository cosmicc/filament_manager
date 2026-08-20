"""Physical nozzle inventory, installation, usage, and lifecycle routes."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import func, select

from filament_manager.models.enums import NozzleStatus
from filament_manager.models.inventory import Nozzle, Printer
from filament_manager.models.operations import NozzleLifecycleEvent
from filament_manager.services.events import add_audit_event
from filament_manager.services.print_statistics import completed_nozzle_usage

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    NozzleCreate,
    NozzleInstallRequest,
    NozzleLifecycleEventResponse,
    NozzleResponse,
    NozzleUpdate,
)

router = APIRouter(prefix="/nozzles", tags=["nozzles"])


async def _get_nozzle(session: DatabaseSession, nozzle_id: UUID, *, lock: bool = False) -> Nozzle:
    query = select(Nozzle).where(Nozzle.id == nozzle_id)
    if lock:
        query = query.with_for_update()
    nozzle = await session.scalar(query)
    if nozzle is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_nozzle", "Nozzle not found")
    return nozzle


async def _nozzle_responses(session: DatabaseSession, nozzles: list[Nozzle]) -> list[NozzleResponse]:
    nozzle_ids = [nozzle.id for nozzle in nozzles]
    usage = await completed_nozzle_usage(session, nozzle_ids)
    installed = {
        nozzle_id: printer_id
        for printer_id, nozzle_id in await session.execute(
            select(Printer.id, Printer.active_nozzle_id).where(Printer.active_nozzle_id.in_(nozzle_ids))
        )
        if nozzle_id is not None
    }
    return [
        NozzleResponse(
            id=nozzle.id,
            nozzle_code=nozzle.nozzle_code,
            diameter_mm=nozzle.diameter_mm,
            material=nozzle.material,
            manufacturer=nozzle.manufacturer,
            product_name=nozzle.product_name,
            coating=nozzle.coating,
            purchase_date=nozzle.purchase_date,
            status=nozzle.status,
            installed_printer_id=installed.get(nozzle.id),
            installed_at=nozzle.installed_at,
            retired_at=nozzle.retired_at,
            notes=nozzle.notes,
            record_version=nozzle.record_version,
            completed_print_count=usage.get(nozzle.id, (0, Decimal("0")))[0],
            completed_filament_weight_g=usage.get(nozzle.id, (0, Decimal("0")))[1],
        )
        for nozzle in nozzles
    ]


def _lifecycle_event(
    *,
    nozzle_id: UUID,
    printer_id: UUID | None,
    event_type: str,
    actor_id: UUID,
    notes: str | None,
    occurred_at: datetime,
) -> NozzleLifecycleEvent:
    """Build one append-only physical nozzle event."""

    return NozzleLifecycleEvent(
        nozzle_id=nozzle_id,
        printer_id=printer_id,
        event_type=event_type,
        performed_by=actor_id,
        source="web",
        notes=notes.strip() if notes else None,
        occurred_at=occurred_at,
        created_at=occurred_at,
    )


@router.get("", response_model=list[NozzleResponse])
async def list_nozzles(
    _: Viewer, session: DatabaseSession, include_retired: bool = False
) -> list[NozzleResponse]:
    """List physical nozzles with exact completed-print usage."""

    query = select(Nozzle).order_by(Nozzle.nozzle_code)
    if not include_retired:
        query = query.where(Nozzle.status != NozzleStatus.RETIRED)
    return await _nozzle_responses(session, list(await session.scalars(query)))


@router.post("", response_model=NozzleResponse, status_code=status.HTTP_201_CREATED)
async def create_nozzle(
    payload: NozzleCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> NozzleResponse:
    """Create a uniquely labelled physical nozzle without assuming installation."""

    code = payload.nozzle_code.upper()
    if await session.scalar(select(Nozzle.id).where(func.lower(Nozzle.nozzle_code) == code.casefold())):
        raise ApiError(status.HTTP_409_CONFLICT, "nozzle_code_exists", "Nozzle code already exists")
    nozzle = Nozzle(
        nozzle_code=code,
        diameter_mm=payload.diameter_mm,
        material=payload.material.strip(),
        manufacturer=payload.manufacturer.strip() if payload.manufacturer else None,
        product_name=payload.product_name.strip() if payload.product_name else None,
        coating=payload.coating.strip() if payload.coating else None,
        purchase_date=payload.purchase_date,
        status=NozzleStatus.AVAILABLE,
        notes=payload.notes.strip() if payload.notes else None,
    )
    session.add(nozzle)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="nozzle.create",
        object_type="nozzle",
        object_id=nozzle.id,
        before=None,
        after={
            "nozzle_code": nozzle.nozzle_code,
            "diameter_mm": str(nozzle.diameter_mm),
            "material": nozzle.material,
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return (await _nozzle_responses(session, [nozzle]))[0]


@router.patch("/{nozzle_id}", response_model=NozzleResponse)
async def update_nozzle(
    nozzle_id: UUID,
    payload: NozzleUpdate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> NozzleResponse:
    """Update nozzle metadata or retire/reactivate an uninstalled nozzle."""

    nozzle = await _get_nozzle(session, nozzle_id, lock=True)
    if nozzle.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "record_version_conflict", "Nozzle changed; reload")
    active_printer = await session.scalar(select(Printer).where(Printer.active_nozzle_id == nozzle.id))
    if payload.retired is True and active_printer is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "installed_nozzle_cannot_retire",
            "Remove the nozzle from its printer before retiring it",
        )
    before: dict[str, object] = {
        "nozzle_code": nozzle.nozzle_code,
        "diameter_mm": str(nozzle.diameter_mm),
        "material": nozzle.material,
        "status": nozzle.status.value,
        "record_version": nozzle.record_version,
    }
    if payload.nozzle_code is not None:
        code = payload.nozzle_code.strip().upper()
        conflict = await session.scalar(
            select(Nozzle.id).where(
                Nozzle.id != nozzle.id,
                func.lower(Nozzle.nozzle_code) == code.casefold(),
            )
        )
        if conflict is not None:
            raise ApiError(status.HTTP_409_CONFLICT, "nozzle_code_exists", "Nozzle code already exists")
        nozzle.nozzle_code = code
    for field in ("diameter_mm", "manufacturer", "product_name", "coating", "purchase_date", "notes"):
        if field in payload.model_fields_set:
            value = getattr(payload, field)
            if isinstance(value, str):
                value = value.strip() or None
            setattr(nozzle, field, value)
    if "material" in payload.model_fields_set:
        if payload.material is None or not payload.material.strip():
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "nozzle_material_required",
                "Material is required",
            )
        nozzle.material = payload.material.strip()
    now = datetime.now(UTC)
    if payload.retired is True and nozzle.status != NozzleStatus.RETIRED:
        nozzle.status = NozzleStatus.RETIRED
        nozzle.retired_at = now
        session.add(
            _lifecycle_event(
                nozzle_id=nozzle.id,
                printer_id=None,
                event_type="retired",
                actor_id=operator.id,
                notes=payload.notes,
                occurred_at=now,
            )
        )
    elif payload.retired is False and nozzle.status == NozzleStatus.RETIRED:
        nozzle.status = NozzleStatus.AVAILABLE
        nozzle.retired_at = None
        session.add(
            _lifecycle_event(
                nozzle_id=nozzle.id,
                printer_id=None,
                event_type="reactivated",
                actor_id=operator.id,
                notes=payload.notes,
                occurred_at=now,
            )
        )
    nozzle.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="nozzle.update",
        object_type="nozzle",
        object_id=nozzle.id,
        before=before,
        after={
            "nozzle_code": nozzle.nozzle_code,
            "status": nozzle.status.value,
            "record_version": nozzle.record_version,
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return (await _nozzle_responses(session, [nozzle]))[0]


@router.post("/{nozzle_id}/install", response_model=NozzleResponse)
async def install_nozzle(
    nozzle_id: UUID,
    payload: NozzleInstallRequest,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> NozzleResponse:
    """Install one physical nozzle and close the previous printer assignment."""

    nozzle = await _get_nozzle(session, nozzle_id, lock=True)
    if nozzle.status == NozzleStatus.RETIRED:
        raise ApiError(status.HTTP_409_CONFLICT, "nozzle_retired", "Reactivate the nozzle before use")
    printer = await session.scalar(select(Printer).where(Printer.id == payload.printer_id).with_for_update())
    if printer is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found")
    other_printer = await session.scalar(
        select(Printer).where(
            Printer.active_nozzle_id == nozzle.id,
            Printer.id != printer.id,
        )
    )
    if other_printer is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "nozzle_already_installed",
            f"Nozzle is already installed on {other_printer.name}",
        )
    if printer.active_nozzle_id == nozzle.id:
        return (await _nozzle_responses(session, [nozzle]))[0]
    now = datetime.now(UTC)
    previous = await session.get(Nozzle, printer.active_nozzle_id) if printer.active_nozzle_id else None
    if previous is not None:
        previous.status = NozzleStatus.AVAILABLE
        previous.installed_at = None
        previous.record_version += 1
        session.add(
            _lifecycle_event(
                nozzle_id=previous.id,
                printer_id=printer.id,
                event_type="removed",
                actor_id=operator.id,
                notes=f"Replaced by {nozzle.nozzle_code}",
                occurred_at=now,
            )
        )
    printer.active_nozzle_id = nozzle.id
    printer.nozzle_diameter_mm = nozzle.diameter_mm
    printer.nozzle_material = nozzle.material
    printer.record_version += 1
    nozzle.status = NozzleStatus.INSTALLED
    nozzle.installed_at = now
    nozzle.record_version += 1
    session.add(
        _lifecycle_event(
            nozzle_id=nozzle.id,
            printer_id=printer.id,
            event_type="installed",
            actor_id=operator.id,
            notes=payload.notes,
            occurred_at=now,
        )
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="nozzle.install",
        object_type="printer",
        object_id=printer.id,
        before={"active_nozzle_id": str(previous.id) if previous else None},
        after={"active_nozzle_id": str(nozzle.id), "nozzle_code": nozzle.nozzle_code},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return (await _nozzle_responses(session, [nozzle]))[0]


@router.post("/{nozzle_id}/remove", response_model=NozzleResponse)
async def remove_nozzle(
    nozzle_id: UUID,
    payload: NozzleInstallRequest,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> NozzleResponse:
    """Record a completed physical nozzle removal from the selected printer."""

    nozzle = await _get_nozzle(session, nozzle_id, lock=True)
    printer = await session.scalar(select(Printer).where(Printer.id == payload.printer_id).with_for_update())
    if printer is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_printer", "Printer not found")
    if printer.active_nozzle_id != nozzle.id:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "nozzle_not_installed",
            "This nozzle is not installed on the selected printer",
        )
    now = datetime.now(UTC)
    printer.active_nozzle_id = None
    printer.record_version += 1
    nozzle.status = NozzleStatus.AVAILABLE
    nozzle.installed_at = None
    nozzle.record_version += 1
    session.add(
        _lifecycle_event(
            nozzle_id=nozzle.id,
            printer_id=printer.id,
            event_type="removed",
            actor_id=operator.id,
            notes=payload.notes,
            occurred_at=now,
        )
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="nozzle.remove",
        object_type="printer",
        object_id=printer.id,
        before={"active_nozzle_id": str(nozzle.id)},
        after={"active_nozzle_id": None},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return (await _nozzle_responses(session, [nozzle]))[0]


@router.get("/{nozzle_id}/events", response_model=list[NozzleLifecycleEventResponse])
async def list_nozzle_events(
    nozzle_id: UUID, _: Viewer, session: DatabaseSession
) -> list[NozzleLifecycleEventResponse]:
    """Return newest-first immutable lifecycle history for one physical nozzle."""

    await _get_nozzle(session, nozzle_id)
    events = await session.scalars(
        select(NozzleLifecycleEvent)
        .where(NozzleLifecycleEvent.nozzle_id == nozzle_id)
        .order_by(NozzleLifecycleEvent.occurred_at.desc())
        .limit(500)
    )
    return [NozzleLifecycleEventResponse.model_validate(event) for event in events]
