"""Canonical vendor, filament, spool, measurement, and label routes."""

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Annotated, Any
from uuid import UUID

import qrcode
from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import ColumnElement

from filament_manager.config import get_settings
from filament_manager.domain.colors import normalize_color_hex, normalize_color_name
from filament_manager.domain.mass import (
    InvalidWeightError,
    MeasurementConfirmationRequired,
    calculate_measurement,
)
from filament_manager.models.enums import MeasurementStatus, ProfileStatus, SpoolStatus
from filament_manager.models.inventory import (
    FilamentColor,
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Spool,
    SpoolMeasurement,
    Vendor,
)
from filament_manager.services.events import add_audit_event, add_outbox_job

from ..dependencies import DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    FilamentColorResponse,
    FilamentCreate,
    FilamentResponse,
    FilamentUpdate,
    MaterialSettingsInput,
    MeasurementCreate,
    MeasurementResponse,
    Page,
    SpoolCreate,
    SpoolResponse,
    SpoolUpdate,
    VendorCreate,
)

router = APIRouter(tags=["inventory"])


async def _remember_color(
    session: DatabaseSession,
    *,
    color_name: str,
    color_hex: str | None,
    actor_id: UUID,
    correlation_id: str,
    exclude_product_id: UUID | None = None,
) -> FilamentColor:
    """Resolve a color name and propagate an explicitly changed screen sample."""

    display_name = color_name.strip()
    normalized_name = normalize_color_name(display_name)
    mapping = await session.scalar(
        select(FilamentColor).where(FilamentColor.normalized_name == normalized_name).with_for_update()
    )
    selected_hex = normalize_color_hex(color_hex) if color_hex else None
    if mapping is None:
        mapping = FilamentColor(
            name=display_name,
            normalized_name=normalized_name,
            color_hex=selected_hex or "808080",
        )
        session.add(mapping)
        await session.flush()
        add_audit_event(
            session,
            actor_id=actor_id,
            source="web",
            action="filament_color.create",
            object_type="filament_color",
            object_id=mapping.id,
            before=None,
            after={"name": mapping.name, "color_hex": mapping.color_hex},
            correlation_id=correlation_id,
        )
        return mapping
    if selected_hex is None or selected_hex == mapping.color_hex:
        return mapping

    previous_hex = mapping.color_hex
    mapping.color_hex = selected_hex
    mapping.record_version += 1
    products = list(await session.scalars(select(FilamentProduct).with_for_update()))
    for product in products:
        if product.id == exclude_product_id:
            continue
        if normalize_color_name(product.color_name) != normalized_name:
            continue
        product.color_name = mapping.name
        product.color_hex = selected_hex
        product.record_version += 1
        add_outbox_job(
            session,
            job_type="spoolman.filament.upsert",
            idempotency_key=f"filament:{product.id}:v{product.record_version}",
            aggregate_type="filament_product",
            aggregate_id=product.id,
            aggregate_version=product.record_version,
            payload={"filament_product_id": str(product.id)},
        )
    add_audit_event(
        session,
        actor_id=actor_id,
        source="web",
        action="filament_color.update",
        object_type="filament_color",
        object_id=mapping.id,
        before={"color_hex": previous_hex},
        after={"name": mapping.name, "color_hex": mapping.color_hex},
        correlation_id=correlation_id,
    )
    return mapping


def spool_response(spool: Spool) -> SpoolResponse:
    """Create the flattened API view required by table and detail screens."""

    product = spool.filament_product
    remaining_percent = (
        (spool.remaining_mass_effective_g / spool.nominal_net_mass_g) * Decimal("100")
    ).quantize(Decimal("0.001"))
    return SpoolResponse(
        id=spool.id,
        spool_code=spool.spool_code,
        filament_product_id=spool.filament_product_id,
        material_type=product.material_type,
        filler=product.filler,
        finish=product.finish,
        color_name=product.color_name,
        color_hex=product.color_hex,
        vendor_name=product.vendor.name if product.vendor else None,
        product_name=product.product_name,
        nominal_net_mass_g=spool.nominal_net_mass_g,
        tare_mass_g=spool.tare_mass_g,
        remaining_mass_expected_g=spool.remaining_mass_expected_g,
        remaining_mass_measured_g=spool.remaining_mass_measured_g,
        remaining_mass_effective_g=spool.remaining_mass_effective_g,
        remaining_percent=remaining_percent,
        weight_confidence=spool.weight_confidence,
        status=spool.status.value,
        location=spool.location,
        spoolman_id=spool.spoolman_id,
        last_measurement_at=spool.last_measurement_at,
        notes=spool.notes,
        archived=spool.archived,
        record_version=spool.record_version,
    )


def filament_response(product: FilamentProduct) -> FilamentResponse:
    """Create a product response with its optional vendor name."""

    return FilamentResponse(
        id=product.id,
        vendor_id=product.vendor_id,
        vendor_name=product.vendor.name if product.vendor else None,
        material_type=product.material_type,
        filler=product.filler,
        finish=product.finish,
        color_name=product.color_name,
        color_hex=product.color_hex,
        product_name=product.product_name,
        diameter_mm=product.diameter_mm,
        tolerance_mm=product.tolerance_mm,
        density_g_cm3=product.density_g_cm3,
        nominal_net_mass_g=product.nominal_net_mass_g,
        notes=product.notes,
        material_template_revision_id=product.source_template_revision_id,
        record_version=product.record_version,
    )


async def _get_spool(session: DatabaseSession, spool_id: UUID | str, *, lock: bool = False) -> Spool:
    query = select(Spool).options(joinedload(Spool.filament_product).joinedload(FilamentProduct.vendor))
    if isinstance(spool_id, UUID):
        query = query.where(Spool.id == spool_id)
    else:
        query = query.where(func.lower(Spool.spool_code) == spool_id.casefold())
    if lock:
        # Lock only the canonical spool row; the eager-loaded optional vendor uses an outer join.
        query = query.with_for_update(of=Spool)
    result = await session.execute(query)
    spool = result.unique().scalar_one_or_none()
    if spool is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_spool", "Spool not found")
    return spool


@router.get("/vendors", response_model=list[dict[str, object]])
async def list_vendors(_: Viewer, session: DatabaseSession) -> list[dict[str, object]]:
    """List controlled manufacturer records."""

    result = await session.execute(select(Vendor).order_by(Vendor.name))
    return [
        {
            "id": vendor.id,
            "name": vendor.name,
            "preferred": vendor.preferred,
            "record_version": vendor.record_version,
        }
        for vendor in result.scalars()
    ]


@router.post("/vendors", status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, object]:
    """Create a canonical filament manufacturer."""

    existing = await session.scalar(
        select(Vendor.id).where(func.lower(Vendor.name) == payload.name.casefold())
    )
    if existing:
        raise ApiError(status.HTTP_409_CONFLICT, "vendor_exists", "Vendor already exists")
    vendor = Vendor(name=payload.name.strip(), preferred=payload.preferred, notes=payload.notes)
    session.add(vendor)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="vendor.create",
        object_type="vendor",
        object_id=vendor.id,
        before=None,
        after={"name": vendor.name, "preferred": vendor.preferred},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"id": vendor.id, "name": vendor.name, "preferred": vendor.preferred}


@router.get("/filaments", response_model=list[FilamentResponse])
async def list_filaments(
    _: Viewer,
    session: DatabaseSession,
    material: str | None = None,
    search: str | None = None,
) -> list[FilamentResponse]:
    """List filament products with optional material and text filters."""

    query = select(FilamentProduct).options(joinedload(FilamentProduct.vendor))
    if material:
        query = query.where(func.lower(FilamentProduct.material_type) == material.casefold())
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                FilamentProduct.product_name.ilike(term),
                FilamentProduct.color_name.ilike(term),
                FilamentProduct.material_type.ilike(term),
            )
        )
    result = await session.execute(query.order_by(FilamentProduct.material_type, FilamentProduct.color_name))
    return [filament_response(item) for item in result.scalars()]


@router.get("/filament-colors", response_model=list[FilamentColorResponse])
async def list_filament_colors(_: Viewer, session: DatabaseSession) -> list[FilamentColor]:
    """List remembered color samples for autocomplete and color pickers."""

    return list(await session.scalars(select(FilamentColor).order_by(FilamentColor.name)))


@router.get("/filaments/{filament_id}", response_model=FilamentResponse)
async def get_filament(
    filament_id: UUID,
    _: Viewer,
    session: DatabaseSession,
) -> FilamentResponse:
    """Return one filament product for its settings detail page."""

    product = await session.scalar(
        select(FilamentProduct)
        .where(FilamentProduct.id == filament_id)
        .options(joinedload(FilamentProduct.vendor))
    )
    if product is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_filament", "Filament not found")
    return filament_response(product)


@router.post("/filaments", response_model=FilamentResponse, status_code=status.HTTP_201_CREATED)
async def create_filament(
    payload: FilamentCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> FilamentResponse:
    """Create a canonical filament product definition."""

    template_revision: MaterialTemplateRevision | None = None
    template: MaterialTemplate | None = None
    if payload.material_template_revision_id is not None:
        template_revision = await session.get(MaterialTemplateRevision, payload.material_template_revision_id)
        if template_revision is None or template_revision.status != ProfileStatus.PUBLISHED:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "template_revision_unavailable",
                "Select a published material template revision",
            )
        template = await session.get(MaterialTemplate, template_revision.material_template_id)
        if template is None or not template.active:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "material_template_inactive",
                "The selected material template is inactive",
            )
        if template.material_type.casefold() != payload.material_type.strip().casefold():
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "material_type_template_mismatch",
                "The filament material type must match the selected template",
            )

    color = await _remember_color(
        session,
        color_name=payload.color_name,
        color_hex=payload.color_hex,
        actor_id=operator.id,
        correlation_id=request.state.correlation_id,
    )
    product_values = payload.model_dump(
        exclude={"material_template_revision_id", "material_type", "color_name", "color_hex"}
    )
    product = FilamentProduct(
        **product_values,
        material_type=payload.material_type.strip(),
        color_name=color.name,
        color_hex=color.color_hex,
        source_template_revision_id=payload.material_template_revision_id,
    )
    session.add(product)
    await session.flush()
    profile: MaterialProfile | None = None
    if template_revision is not None and template is not None:
        profile_values = MaterialSettingsInput.model_validate(template_revision.settings).model_dump()
        # Product density is canonical for the actual purchasable filament and
        # intentionally supersedes the generic template's starting density.
        profile_values["filament_density_g_cm3"] = product.density_g_cm3
        profile = MaterialProfile(
            **profile_values,
            filament_product_id=product.id,
            printer_id=template.printer_id,
            nozzle_diameter_mm=template.nozzle_diameter_mm,
            version=1,
            status=ProfileStatus.DRAFT,
            source_template_revision_id=template_revision.id,
        )
        session.add(profile)
        await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="filament.create",
        object_type="filament_product",
        object_id=product.id,
        before=None,
        after={
            "material_type": product.material_type,
            "color_name": product.color_name,
            "source_template_revision_id": (
                str(template_revision.id) if template_revision is not None else None
            ),
            "material_profile_id": str(profile.id) if profile is not None else None,
        },
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="spoolman.filament.upsert",
        idempotency_key=f"filament:{product.id}:v1",
        aggregate_type="filament_product",
        aggregate_id=product.id,
        aggregate_version=1,
        payload={"filament_product_id": str(product.id)},
    )
    await session.commit()
    await session.refresh(product, attribute_names=["vendor"])
    return filament_response(product)


@router.patch("/filaments/{filament_id}", response_model=FilamentResponse)
async def update_filament(
    filament_id: UUID,
    payload: FilamentUpdate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> FilamentResponse:
    """Update product metadata and apply its color sample to matching products."""

    product = await session.scalar(
        select(FilamentProduct).where(FilamentProduct.id == filament_id).with_for_update()
    )
    if product is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_filament", "Filament not found")
    if product.record_version != payload.expected_version:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "record_version_conflict",
            "Filament changed; reload and retry",
        )
    if payload.vendor_id is not None and await session.get(Vendor, payload.vendor_id) is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_vendor", "Vendor not found")

    before: dict[str, object] = {
        "material_type": product.material_type,
        "color_name": product.color_name,
        "color_hex": product.color_hex,
        "record_version": product.record_version,
    }
    color_name = payload.color_name if payload.color_name is not None else product.color_name
    requested_hex = payload.color_hex if "color_hex" in payload.model_fields_set else product.color_hex
    color = await _remember_color(
        session,
        color_name=color_name,
        color_hex=requested_hex,
        actor_id=operator.id,
        correlation_id=request.state.correlation_id,
        exclude_product_id=product.id,
    )
    product.color_name = color.name
    product.color_hex = color.color_hex
    if "vendor_id" in payload.model_fields_set:
        product.vendor_id = payload.vendor_id
    for field in (
        "material_type",
        "diameter_mm",
        "tolerance_mm",
        "density_g_cm3",
        "nominal_net_mass_g",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(product, field, value.strip() if isinstance(value, str) else value)
    for field in ("filler", "finish", "product_name", "notes"):
        if field in payload.model_fields_set:
            value = getattr(payload, field)
            setattr(product, field, value.strip() or None if isinstance(value, str) else value)
    product.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="filament.update",
        object_type="filament_product",
        object_id=product.id,
        before=before,
        after={
            "material_type": product.material_type,
            "color_name": product.color_name,
            "color_hex": product.color_hex,
            "record_version": product.record_version,
        },
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="spoolman.filament.upsert",
        idempotency_key=f"filament:{product.id}:v{product.record_version}",
        aggregate_type="filament_product",
        aggregate_id=product.id,
        aggregate_version=product.record_version,
        payload={"filament_product_id": str(product.id)},
    )
    await session.commit()
    await session.refresh(product, attribute_names=["vendor"])
    return filament_response(product)


@router.get("/spools", response_model=Page)
async def list_spools(
    _: Viewer,
    session: DatabaseSession,
    search: str | None = None,
    material: str | None = None,
    spool_status: Annotated[str | None, Query(alias="status")] = None,
    manufacturer: str | None = None,
    location: str | None = None,
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page:
    """Search and page physical spools for the inventory table."""

    filters: list[ColumnElement[bool]] = []
    if not include_archived:
        filters.append(Spool.archived.is_(False))
    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Spool.spool_code.ilike(term),
                FilamentProduct.material_type.ilike(term),
                FilamentProduct.color_name.ilike(term),
                FilamentProduct.product_name.ilike(term),
                Spool.location.ilike(term),
            )
        )
    if material:
        filters.append(func.lower(FilamentProduct.material_type) == material.casefold())
    if spool_status:
        try:
            filters.append(Spool.status == SpoolStatus(spool_status))
        except ValueError as exc:
            raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_status", "Unknown status") from exc
    if manufacturer:
        filters.append(Vendor.name.ilike(f"%{manufacturer.strip()}%"))
    if location:
        filters.append(Spool.location.ilike(f"%{location.strip()}%"))

    base = select(Spool).join(Spool.filament_product).outerjoin(FilamentProduct.vendor).where(*filters)
    count = await session.scalar(select(func.count()).select_from(base.subquery()))
    result = await session.execute(
        base.options(joinedload(Spool.filament_product).joinedload(FilamentProduct.vendor))
        .order_by(Spool.spool_code)
        .limit(limit)
        .offset(offset)
    )
    return Page(
        items=[spool_response(spool).model_dump(mode="json") for spool in result.unique().scalars()],
        total=count or 0,
        limit=limit,
        offset=offset,
    )


@router.post("/spools", response_model=SpoolResponse, status_code=status.HTTP_201_CREATED)
async def create_spool(
    payload: SpoolCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> SpoolResponse:
    """Create a physical spool and queue its external projection atomically."""

    if await session.scalar(
        select(Spool.id).where(func.lower(Spool.spool_code) == payload.spool_code.casefold())
    ):
        raise ApiError(status.HTTP_409_CONFLICT, "spool_code_exists", "Spool code already exists")
    product = await session.get(FilamentProduct, payload.filament_product_id)
    if product is None:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_filament", "Filament not found")

    measured = None
    effective = payload.nominal_net_mass_g
    confidence = "estimated"
    spool_status = SpoolStatus.NEEDS_WEIGHING
    if payload.initial_gross_mass_g is not None:
        try:
            calculation = calculate_measurement(
                gross_mass_g=payload.initial_gross_mass_g,
                tare_mass_g=payload.tare_mass_g,
                nominal_mass_g=payload.nominal_net_mass_g,
                expected_remaining_g=payload.nominal_net_mass_g,
                low_threshold_percent=Decimal(str(get_settings().sync.low_spool_threshold_percent)),
                increase_tolerance_percent=Decimal(
                    str(get_settings().sync.measurement_increase_tolerance_percent)
                ),
                increase_tolerance_g=Decimal(str(get_settings().sync.measurement_increase_tolerance_g)),
                confirmed=True,
            )
        except InvalidWeightError as exc:
            raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_weight", str(exc)) from exc
        measured = calculation.net_mass_g
        effective = calculation.net_mass_g
        confidence = "measured"
        spool_status = calculation.spool_status

    spool = Spool(
        spool_code=payload.spool_code.upper(),
        filament_product_id=payload.filament_product_id,
        nominal_net_mass_g=payload.nominal_net_mass_g,
        tare_mass_g=payload.tare_mass_g,
        remaining_mass_expected_g=payload.nominal_net_mass_g,
        remaining_mass_measured_g=measured,
        remaining_mass_effective_g=effective,
        weight_confidence=confidence,
        status=spool_status,
        purchase_source=payload.purchase_source,
        purchase_date=payload.purchase_date,
        purchase_cost=payload.purchase_cost,
        currency=payload.currency,
        location=payload.location,
        location_authoritative=True,
        notes=payload.notes,
    )
    session.add(spool)
    await session.flush()
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="spool.create",
        object_type="spool",
        object_id=spool.id,
        before=None,
        after={"spool_code": spool.spool_code, "remaining_mass_effective_g": str(effective)},
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="spoolman.spool.upsert",
        idempotency_key=f"spool:{spool.id}:v1",
        aggregate_type="spool",
        aggregate_id=spool.id,
        aggregate_version=1,
        payload={"spool_id": str(spool.id)},
    )
    await session.commit()
    spool.filament_product = product
    return spool_response(spool)


@router.get("/spools/{spool_id}", response_model=SpoolResponse)
async def get_spool(spool_id: UUID, _: Viewer, session: DatabaseSession) -> SpoolResponse:
    """Return one physical spool by UUID."""

    return spool_response(await _get_spool(session, spool_id))


@router.get("/spools/by-code/{spool_code}", response_model=SpoolResponse)
async def get_spool_by_code(spool_code: str, _: Viewer, session: DatabaseSession) -> SpoolResponse:
    """Resolve a scanned or typed immutable human spool code."""

    return spool_response(await _get_spool(session, spool_code))


@router.patch("/spools/{spool_id}", response_model=SpoolResponse)
async def update_spool(
    spool_id: UUID,
    payload: SpoolUpdate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> SpoolResponse:
    """Update mutable spool metadata with optimistic concurrency."""

    spool = await _get_spool(session, spool_id, lock=True)
    if spool.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "record_version_conflict", "Spool changed; reload and retry")
    before = {
        field: getattr(spool, field) for field in payload.model_fields_set if field != "expected_version"
    }
    for field in payload.model_fields_set - {"expected_version"}:
        setattr(spool, field, getattr(payload, field))
    if "location" in payload.model_fields_set:
        # A browser edit, including clearing the field, permanently establishes
        # Filament Manager as the owner instead of re-importing a remote value.
        spool.location_authoritative = True
    spool.record_version += 1
    after = {field: getattr(spool, field) for field in before}
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="spool.update",
        object_type="spool",
        object_id=spool.id,
        before={key: str(value) if value is not None else None for key, value in before.items()},
        after={key: str(value) if value is not None else None for key, value in after.items()},
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="spoolman.spool.upsert",
        idempotency_key=f"spool:{spool.id}:v{spool.record_version}",
        aggregate_type="spool",
        aggregate_id=spool.id,
        aggregate_version=spool.record_version,
        payload={"spool_id": str(spool.id)},
    )
    await session.commit()
    return spool_response(spool)


@router.get("/spools/{spool_id}/measurements", response_model=list[MeasurementResponse])
async def list_measurements(spool_id: UUID, _: Viewer, session: DatabaseSession) -> list[MeasurementResponse]:
    """Return immutable measurement history newest first."""

    await _get_spool(session, spool_id)
    result = await session.execute(
        select(SpoolMeasurement)
        .where(SpoolMeasurement.spool_id == spool_id)
        .order_by(SpoolMeasurement.measured_at.desc())
    )
    return [MeasurementResponse.model_validate(item) for item in result.scalars()]


@router.post(
    "/spools/{spool_id}/measurements",
    response_model=MeasurementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_measurement(
    spool_id: UUID,
    payload: MeasurementCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> MeasurementResponse:
    """Record an immutable physical observation and correction transaction."""

    existing = await session.scalar(
        select(SpoolMeasurement).where(
            SpoolMeasurement.spool_id == spool_id,
            SpoolMeasurement.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return MeasurementResponse.model_validate(existing)

    spool = await _get_spool(session, spool_id, lock=True)
    if payload.allow_above_nominal and operator.role.value != "administrator":
        raise ApiError(status.HTTP_403_FORBIDDEN, "forbidden", "Administrator override required")
    if spool.tare_mass_g <= 0 and payload.tare_mass_g is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "tare_required",
            "Enter the verified empty-spool tare before recording this measurement",
        )
    if spool.tare_mass_g > 0 and payload.tare_mass_g is not None and payload.tare_mass_g != spool.tare_mass_g:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "tare_change_requires_review",
            "The supplied tare does not match the stored tare",
        )
    effective_tare = payload.tare_mass_g or spool.tare_mass_g
    settings = get_settings()
    try:
        calculation = calculate_measurement(
            gross_mass_g=payload.gross_mass_g,
            tare_mass_g=effective_tare,
            nominal_mass_g=spool.nominal_net_mass_g,
            expected_remaining_g=spool.remaining_mass_expected_g,
            low_threshold_percent=Decimal(str(settings.sync.low_spool_threshold_percent)),
            increase_tolerance_percent=Decimal(str(settings.sync.measurement_increase_tolerance_percent)),
            increase_tolerance_g=Decimal(str(settings.sync.measurement_increase_tolerance_g)),
            confirmed=payload.confirmed,
            allow_above_nominal=payload.allow_above_nominal,
        )
    except MeasurementConfirmationRequired as exc:
        raise ApiError(status.HTTP_409_CONFLICT, "measurement_confirmation_required", str(exc)) from exc
    except InvalidWeightError as exc:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_weight", str(exc)) from exc

    measured_at = payload.measured_at or datetime.now(UTC)
    if measured_at.tzinfo is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_timestamp", "Timestamp must include timezone"
        )
    measurement = SpoolMeasurement(
        spool_id=spool.id,
        source=payload.source,
        status=MeasurementStatus.ACCEPTED,
        gross_mass_g=payload.gross_mass_g,
        tare_mass_g=effective_tare,
        net_mass_g=calculation.net_mass_g,
        expected_before_g=spool.remaining_mass_expected_g,
        variance_g=calculation.variance_g,
        confidence="physical",
        requires_confirmation=calculation.requires_confirmation,
        confirmed=payload.confirmed,
        idempotency_key=idempotency_key,
        operator_id=operator.id,
        notes=payload.notes,
        measured_at=measured_at,
        created_at=datetime.now(UTC),
    )
    session.add(measurement)
    await session.flush()
    if spool.tare_mass_g <= 0:
        spool.tare_mass_g = effective_tare
    spool.remaining_mass_measured_g = calculation.net_mass_g
    spool.remaining_mass_expected_g = calculation.net_mass_g
    spool.remaining_mass_effective_g = calculation.net_mass_g
    spool.weight_confidence = "measured"
    spool.status = calculation.spool_status
    spool.last_measurement_at = measured_at
    spool.record_version += 1
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="spool.measurement.accept",
        object_type="spool_measurement",
        object_id=measurement.id,
        before={"expected_remaining_g": str(measurement.expected_before_g)},
        after={
            "measured_remaining_g": str(measurement.net_mass_g),
            "variance_g": str(measurement.variance_g),
        },
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="spoolman.spool.adjust_weight",
        idempotency_key=f"measurement:{measurement.id}",
        aggregate_type="spool",
        aggregate_id=spool.id,
        aggregate_version=spool.record_version,
        payload={"spool_id": str(spool.id), "remaining_mass_g": str(calculation.net_mass_g)},
    )
    add_outbox_job(
        session,
        job_type="google.inventory.publish",
        idempotency_key=f"spool:{spool.id}:google:v{spool.record_version}",
        aggregate_type="spool",
        aggregate_id=spool.id,
        aggregate_version=spool.record_version,
        payload={"spool_id": str(spool.id)},
    )
    await session.commit()
    return MeasurementResponse.model_validate(measurement)


@router.post("/spools/{spool_id}/set-active", status_code=status.HTTP_202_ACCEPTED)
async def set_active_spool(
    spool_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Queue a supported Moonraker active-spool request."""

    spool = await _get_spool(session, spool_id)
    if spool.spoolman_id is None:
        raise ApiError(status.HTTP_409_CONFLICT, "spool_not_projected", "Project spool to Spoolman first")
    add_outbox_job(
        session,
        job_type="moonraker.active_spool.set",
        idempotency_key=f"active-spool:{spool.id}:v{spool.record_version}",
        aggregate_type="spool",
        aggregate_id=spool.id,
        aggregate_version=spool.record_version,
        payload={"spoolman_id": spool.spoolman_id},
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="spool.set_active.requested",
        object_type="spool",
        object_id=spool.id,
        before=None,
        after={"spoolman_id": spool.spoolman_id},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"status": "queued"}


@router.get("/spools/{spool_id}/label")
async def spool_label(spool_id: UUID, _: Viewer, session: DatabaseSession) -> StreamingResponse:
    """Generate a QR code containing only a stable spool URL."""

    spool = await _get_spool(session, spool_id)
    url = f"{str(get_settings().app.base_url).rstrip('/')}/spools/{spool.id}"
    image: Any = qrcode.make(url)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    headers = {"Content-Disposition": f'inline; filename="spool-{spool.spool_code}.png"'}
    return StreamingResponse(buffer, media_type="image/png", headers=headers)
