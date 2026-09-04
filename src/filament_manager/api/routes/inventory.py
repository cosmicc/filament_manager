"""Canonical vendor, filament, spool, measurement, and label routes."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import ColumnElement

from filament_manager.config import get_settings
from filament_manager.domain.colors import (
    normalize_color_hex,
    normalize_color_name,
    normalize_color_palette,
)
from filament_manager.domain.mass import (
    InvalidWeightError,
    MeasurementConfirmationRequired,
    calculate_measurement,
)
from filament_manager.domain.profile_inheritance import resolve_profile_settings
from filament_manager.domain.spool_preflight import SpoolPreflightError
from filament_manager.models.calibration import CalibrationSession
from filament_manager.models.enums import (
    MeasurementSource,
    MeasurementStatus,
    ProfileStatus,
    SpoolStatus,
)
from filament_manager.models.inventory import (
    FilamentColor,
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Spool,
    SpoolMeasurement,
    SpoolUsageEvent,
    Vendor,
)
from filament_manager.models.operations import NfcTag, ProjectionState
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.models.workstations import CuraDeployment
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.filament_defaults import queue_filament_default_projection
from filament_manager.services.material_settings import (
    create_published_profile_snapshot,
    queue_managed_cura_library,
)
from filament_manager.services.print_statistics import completed_spool_print_counts
from filament_manager.services.spool_labels import render_spool_label_png
from filament_manager.services.spool_preflight import spool_change_target

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


@dataclass(frozen=True)
class ResolvedFilamentColor:
    """A validated product palette, independent of remembered-color storage."""

    name: str
    color_hex: str
    color_mode: str
    color_hexes: list[str]


def _resolved_color(mapping: FilamentColor) -> ResolvedFilamentColor:
    """Copy a persisted remembered color into the product-facing value shape."""

    return ResolvedFilamentColor(
        name=mapping.name,
        color_hex=mapping.color_hex,
        color_mode=mapping.color_mode,
        color_hexes=mapping.color_hexes,
    )


@router.post("/printer-context/active-spool/clear", status_code=status.HTTP_202_ACCEPTED)
async def request_active_spool_unload(
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Queue a physical unload; canonical/Spoolman state clears only after motion."""

    configured_code = get_settings().moonraker.printers[0].id
    printer = await session.scalar(select(Printer).where(Printer.printer_code == configured_code))
    if printer is None:
        raise ApiError(status.HTTP_409_CONFLICT, "printer_not_configured", "Printer is not ready")
    spool = await session.scalar(select(Spool).where(Spool.active_printer_id == printer.id))
    if spool is None:
        raise ApiError(status.HTTP_409_CONFLICT, "no_active_spool", "No spool is physically loaded")
    add_outbox_job(
        session,
        job_type="moonraker.spool_unload.request",
        idempotency_key=f"spool-unload:{printer.id}:{request.state.correlation_id}",
        aggregate_type="printer",
        aggregate_id=printer.id,
        aggregate_version=printer.record_version,
        payload={"printer_id": str(printer.id)},
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="spool.unload.request",
        object_type="printer",
        object_id=printer.id,
        before={"active_spool_id": str(spool.id), "spoolman_id": spool.spoolman_id},
        after={"physical_unload_queued": True},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"status": "unload_queued", "printer_name": printer.name}


async def _remember_color(
    session: DatabaseSession,
    *,
    color_name: str,
    color_hex: str | None,
    color_mode: str,
    color_hexes: list[str] | None,
    actor_id: UUID,
    correlation_id: str,
    exclude_product_id: UUID | None = None,
) -> ResolvedFilamentColor:
    """Resolve a product palette and remember only shared solid/rainbow colors."""

    display_name = color_name.strip()
    normalized_name = normalize_color_name(display_name)
    if normalized_name == "rainbow":
        color_mode = "rainbow"
        color_hexes = []
    if color_mode.strip().casefold() == "multicolor":
        try:
            selected_mode, selected_palette = normalize_color_palette(
                color_mode,
                color_hex,
                color_hexes,
            )
        except ValueError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_color_palette",
                str(exc),
            ) from exc
        return ResolvedFilamentColor(
            name=display_name,
            color_hex=selected_palette[0],
            color_mode=selected_mode,
            color_hexes=selected_palette,
        )
    mapping = await session.scalar(
        select(FilamentColor).where(FilamentColor.normalized_name == normalized_name).with_for_update()
    )
    if mapping is not None and normalized_name != "rainbow" and color_hex is None and not color_hexes:
        # Selecting an existing remembered name without resubmitting a sample
        # means "reuse it", preserving backward-compatible API behavior.
        return _resolved_color(mapping)
    try:
        selected_mode, selected_palette = normalize_color_palette(
            color_mode,
            color_hex,
            color_hexes,
        )
    except ValueError as exc:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_color_palette",
            str(exc),
        ) from exc
    selected_hex = selected_palette[0]
    if mapping is None:
        mapping = FilamentColor(
            name=display_name,
            normalized_name=normalized_name,
            color_hex=selected_hex or "808080",
            color_mode=selected_mode,
            color_hexes=selected_palette,
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
            after={
                "name": mapping.name,
                "color_hex": mapping.color_hex,
                "color_mode": mapping.color_mode,
                "color_hexes": mapping.color_hexes,
            },
            correlation_id=correlation_id,
        )
        return _resolved_color(mapping)
    if (
        selected_hex == mapping.color_hex
        and selected_mode == mapping.color_mode
        and selected_palette == mapping.color_hexes
    ):
        return _resolved_color(mapping)

    previous: dict[str, object] = {
        "color_hex": mapping.color_hex,
        "color_mode": mapping.color_mode,
        "color_hexes": mapping.color_hexes,
    }
    products = list(await session.scalars(select(FilamentProduct).with_for_update()))
    # Solid named colors remain shared screen samples. Multicolor palettes are
    # product-owned so two filaments with the same descriptive name can retain
    # different physical segment colors. Rainbow is a fixed special color.
    affected_products = (
        [
            product
            for product in products
            if product.id != exclude_product_id
            and normalize_color_name(product.color_name) == normalized_name
            and product.color_mode == "solid"
        ]
        if selected_mode == "solid" and mapping.color_mode == "solid"
        else []
    )
    if affected_products and await _filaments_have_recorded_use(
        session, [product.id for product in affected_products]
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "color_in_use",
            "This remembered color is locked because a matching filament has recorded use",
        )
    mapping.color_hex = selected_hex
    mapping.color_mode = selected_mode
    mapping.color_hexes = selected_palette
    mapping.record_version += 1
    for product in affected_products:
        product.color_name = mapping.name
        product.color_hex = selected_hex
        product.color_mode = selected_mode
        product.color_hexes = selected_palette
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
        before=previous,
        after={
            "name": mapping.name,
            "color_hex": mapping.color_hex,
            "color_mode": mapping.color_mode,
            "color_hexes": mapping.color_hexes,
        },
        correlation_id=correlation_id,
    )
    return _resolved_color(mapping)


async def _filaments_have_recorded_use(
    session: DatabaseSession,
    filament_ids: list[UUID],
) -> bool:
    """Return whether any selected product is already part of immutable use history."""

    if not filament_ids:
        return False
    usage = await session.scalar(
        select(SpoolUsageEvent.id)
        .join(Spool, Spool.id == SpoolUsageEvent.spool_id)
        .where(Spool.filament_product_id.in_(filament_ids))
        .limit(1)
    )
    if usage is not None:
        return True
    print_job = await session.scalar(
        select(PrintJob.id).where(PrintJob.filament_product_id.in_(filament_ids)).limit(1)
    )
    if print_job is not None:
        return True
    print_segment = await session.scalar(
        select(PrintMaterialSegment.id)
        .where(PrintMaterialSegment.filament_product_id.in_(filament_ids))
        .limit(1)
    )
    return print_segment is not None


def spool_response(spool: Spool, *, completed_print_count: int = 0) -> SpoolResponse:
    """Create the flattened API view required by table and detail screens."""

    product = spool.filament_product
    cost_per_gram = (
        (spool.purchase_cost / spool.nominal_net_mass_g).quantize(Decimal("0.000001"))
        if spool.purchase_cost is not None
        else None
    )
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
        color_mode=product.color_mode,
        color_hexes=product.color_hexes,
        vendor_name=product.vendor.name if product.vendor else None,
        product_name=product.display_name,
        nominal_net_mass_g=spool.nominal_net_mass_g,
        tare_mass_g=spool.tare_mass_g,
        remaining_mass_expected_g=spool.remaining_mass_expected_g,
        remaining_mass_measured_g=spool.remaining_mass_measured_g,
        remaining_mass_effective_g=spool.remaining_mass_effective_g,
        remaining_percent=remaining_percent,
        weight_confidence=spool.weight_confidence,
        status=spool.status.value,
        purchase_source=spool.purchase_source,
        purchase_date=spool.purchase_date,
        purchase_cost=spool.purchase_cost,
        cost_per_gram=cost_per_gram,
        currency=spool.currency,
        location=spool.location,
        spoolman_id=spool.spoolman_id,
        active_printer_id=spool.active_printer_id,
        last_measurement_at=spool.last_measurement_at,
        notes=spool.notes,
        archived=spool.archived,
        record_version=spool.record_version,
        completed_print_count=completed_print_count,
    )


async def spool_response_with_statistics(session: DatabaseSession, spool: Spool) -> SpoolResponse:
    """Return one flattened spool with its distinct completed-print count."""

    counts = await completed_spool_print_counts(session, [spool.id])
    return spool_response(spool, completed_print_count=counts.get(spool.id, 0))


def filament_response(product: FilamentProduct, *, color_editable: bool = True) -> FilamentResponse:
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
        color_mode=product.color_mode,
        color_hexes=product.color_hexes,
        product_name=product.display_name,
        diameter_mm=product.diameter_mm,
        tolerance_mm=product.tolerance_mm,
        density_g_cm3=product.density_g_cm3,
        nominal_net_mass_g=product.nominal_net_mass_g,
        notes=product.notes,
        material_template_revision_id=product.source_template_revision_id,
        archived=product.archived,
        color_editable=color_editable,
        record_version=product.record_version,
    )


async def _current_product_profiles(
    session: DatabaseSession,
    product_id: UUID,
    *,
    lock: bool = False,
) -> list[MaterialProfile]:
    """Return the newest published profile for every exact product scope."""

    query = (
        select(MaterialProfile)
        .where(
            MaterialProfile.filament_product_id == product_id,
            MaterialProfile.status == ProfileStatus.PUBLISHED,
        )
        .order_by(
            MaterialProfile.printer_id,
            MaterialProfile.nozzle_diameter_mm,
            MaterialProfile.version.desc(),
        )
    )
    if lock:
        query = query.with_for_update()
    profiles = list(await session.scalars(query))
    current: dict[tuple[UUID, Decimal], MaterialProfile] = {}
    for profile in profiles:
        current.setdefault((profile.printer_id, profile.nozzle_diameter_mm), profile)
    return list(current.values())


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


async def _projection_state(
    session: DatabaseSession,
    object_type: str,
    object_id: UUID,
) -> ProjectionState | None:
    """Return the current Spoolman projection pointer for a canonical object."""

    return cast(
        ProjectionState | None,
        await session.scalar(
            select(ProjectionState).where(
                ProjectionState.system == "spoolman",
                ProjectionState.object_type == object_type,
                ProjectionState.object_id == object_id,
            )
        ),
    )


async def _spool_has_retained_history(session: DatabaseSession, spool_id: UUID) -> bool:
    """Return whether a spool has history beyond its removable creation measurement."""

    dependency_checks = (
        select(func.count(SpoolMeasurement.id)).where(
            SpoolMeasurement.spool_id == spool_id,
            SpoolMeasurement.idempotency_key != f"initial-{spool_id}",
        ),
        select(func.count(SpoolUsageEvent.id)).where(SpoolUsageEvent.spool_id == spool_id),
        select(func.count(CalibrationSession.id)).where(CalibrationSession.spool_id == spool_id),
        select(func.count(PrintJob.id)).where(PrintJob.spool_id == spool_id),
        select(func.count(PrintMaterialSegment.id)).where(PrintMaterialSegment.spool_id == spool_id),
        select(func.count(NfcTag.id)).where(NfcTag.spool_id == spool_id),
    )
    for dependency_query in dependency_checks:
        if (await session.scalar(dependency_query) or 0) > 0:
            return True
    return False


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
    include_archived: bool = False,
) -> list[FilamentResponse]:
    """List filament products with optional material and text filters."""

    query = select(FilamentProduct).options(joinedload(FilamentProduct.vendor))
    if not include_archived:
        query = query.where(FilamentProduct.archived.is_(False))
    if material:
        query = query.where(func.lower(FilamentProduct.material_type) == material.casefold())
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                FilamentProduct.product_name.ilike(term),
                FilamentProduct.color_name.ilike(term),
                FilamentProduct.material_type.ilike(term),
                FilamentProduct.filler.ilike(term),
                FilamentProduct.finish.ilike(term),
            )
        )
    result = await session.execute(query.order_by(FilamentProduct.material_type, FilamentProduct.color_name))
    return [filament_response(item) for item in result.scalars()]


@router.get("/filament-colors", response_model=list[FilamentColorResponse])
async def list_filament_colors(_: Viewer, session: DatabaseSession) -> list[FilamentColor]:
    """List shared solid and fixed-rainbow samples for color pickers."""

    return list(
        await session.scalars(
            select(FilamentColor).where(FilamentColor.color_mode != "multicolor").order_by(FilamentColor.name)
        )
    )


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
    return filament_response(
        product,
        color_editable=not await _filaments_have_recorded_use(session, [product.id]),
    )


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
    duplicate_source: FilamentProduct | None = None
    duplicate_source_profile: MaterialProfile | None = None
    if payload.duplicate_source_filament_id is not None:
        duplicate_source = await session.get(FilamentProduct, payload.duplicate_source_filament_id)
        if duplicate_source is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "duplicate_source_unavailable",
                "The source filament is no longer available",
            )
        if payload.material_template_revision_id is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "duplicate_template_required",
                "The duplicate must retain the source filament's current template",
            )
    if payload.material_template_revision_id is not None:
        template_revision = await session.get(MaterialTemplateRevision, payload.material_template_revision_id)
        if template_revision is None or template_revision.status != ProfileStatus.PUBLISHED:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "template_revision_unavailable",
                "Select a current material template",
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
        if duplicate_source is not None:
            if duplicate_source.material_type.casefold() != template.material_type.casefold():
                raise ApiError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "duplicate_template_scope_mismatch",
                    "The duplicate must use the source material, printer, and nozzle template scope",
                )
            duplicate_source_profile = await session.scalar(
                select(MaterialProfile)
                .where(
                    MaterialProfile.filament_product_id == duplicate_source.id,
                    MaterialProfile.printer_id == template.printer_id,
                    MaterialProfile.nozzle_diameter_mm == template.nozzle_diameter_mm,
                    MaterialProfile.status == ProfileStatus.PUBLISHED,
                )
                .order_by(MaterialProfile.version.desc())
                .limit(1)
            )
            if duplicate_source_profile is None:
                raise ApiError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "duplicate_source_profile_unavailable",
                    "The source filament does not have print settings for the selected scope",
                )

    color = await _remember_color(
        session,
        color_name=payload.color_name,
        color_hex=payload.color_hex,
        color_mode=payload.color_mode,
        color_hexes=payload.color_hexes,
        actor_id=operator.id,
        correlation_id=request.state.correlation_id,
    )
    product_values = payload.model_dump(
        exclude={
            "material_template_revision_id",
            "duplicate_source_filament_id",
            "material_type",
            "color_name",
            "color_hex",
            "color_mode",
            "color_hexes",
        }
    )
    product = FilamentProduct(
        **product_values,
        material_type=payload.material_type.strip(),
        color_name=color.name,
        color_hex=color.color_hex,
        color_mode=color.color_mode,
        color_hexes=color.color_hexes,
        source_template_revision_id=payload.material_template_revision_id,
    )
    session.add(product)
    await session.flush()
    profile: MaterialProfile | None = None
    if template_revision is not None and template is not None:
        inherited_overrides = (
            dict(duplicate_source_profile.setting_overrides or {})
            if duplicate_source_profile is not None
            else None
        )
        if inherited_overrides is not None:
            template_density = Decimal(str(template_revision.settings["filament_density_g_cm3"]))
            if product.density_g_cm3 == template_density:
                inherited_overrides.pop("filament_density_g_cm3", None)
            else:
                inherited_overrides["filament_density_g_cm3"] = format(
                    product.density_g_cm3,
                    "f",
                )
        profile_values = (
            resolve_profile_settings(
                template_revision.settings,
                inherited_overrides or {},
            )
            if duplicate_source_profile is not None
            else MaterialSettingsInput.model_validate(template_revision.settings).model_dump(mode="json")
        )
        # Product density is canonical for the actual purchasable filament and
        # intentionally supersedes the generic template's starting density.
        profile_values["filament_density_g_cm3"] = product.density_g_cm3
        profile = await create_published_profile_snapshot(
            session,
            filament_product_id=product.id,
            printer_id=template.printer_id,
            nozzle_diameter_mm=template.nozzle_diameter_mm,
            base_revision=template_revision,
            settings=profile_values,
            setting_overrides=inherited_overrides,
        )
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
            "duplicate_source_filament_id": (
                str(payload.duplicate_source_filament_id)
                if payload.duplicate_source_filament_id is not None
                else None
            ),
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
    if profile is not None:
        await queue_managed_cura_library(session, requested_by=operator.id)
    # Validate the exact API representation before committing. This keeps a
    # future response-contract regression from persisting a mutation that the
    # client is subsequently unable to read back.
    await session.flush()
    await session.refresh(product, attribute_names=["vendor"])
    response = filament_response(
        product,
        color_editable=not await _filaments_have_recorded_use(session, [product.id]),
    )
    await session.commit()
    return response


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

    requested_material_type = (
        payload.material_type.strip() if payload.material_type is not None else product.material_type
    )
    target_revision: MaterialTemplateRevision | None = None
    target_template: MaterialTemplate | None = None
    if "material_template_revision_id" in payload.model_fields_set:
        if payload.material_template_revision_id is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "template_revision_unavailable",
                "Select a current material template",
            )
        target_revision = await session.get(MaterialTemplateRevision, payload.material_template_revision_id)
        if target_revision is None or target_revision.status != ProfileStatus.PUBLISHED:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "template_revision_unavailable",
                "Select a current material template",
            )
        target_template = await session.get(MaterialTemplate, target_revision.material_template_id)
        if target_template is None or not target_template.active:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "material_template_inactive",
                "The selected material template is inactive",
            )
        if target_template.material_type.casefold() != requested_material_type.casefold():
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "material_type_template_mismatch",
                "The filament material type must match the selected template",
            )

    before: dict[str, object] = {
        "material_type": product.material_type,
        "color_name": product.color_name,
        "color_hex": product.color_hex,
        "color_mode": product.color_mode,
        "color_hexes": product.color_hexes,
        "record_version": product.record_version,
        "source_template_revision_id": (
            str(product.source_template_revision_id)
            if product.source_template_revision_id is not None
            else None
        ),
        "archived": product.archived,
    }
    color_name = payload.color_name if payload.color_name is not None else product.color_name
    requested_hex = payload.color_hex if "color_hex" in payload.model_fields_set else product.color_hex
    requested_mode = (
        payload.color_mode
        if "color_mode" in payload.model_fields_set and payload.color_mode is not None
        else product.color_mode
    )
    requested_palette = (
        payload.color_hexes
        if "color_hexes" in payload.model_fields_set and payload.color_hexes is not None
        else product.color_hexes
    )
    if "color_hex" in payload.model_fields_set and "color_hexes" not in payload.model_fields_set:
        if requested_mode == "solid":
            requested_palette = [requested_hex or "808080"]
        elif requested_mode == "multicolor":
            requested_palette = [requested_hex or "808080", *requested_palette[1:]]
    current_palette = product.color_hexes or [product.color_hex or "808080"]
    comparison_palette = requested_palette or [requested_hex or "808080"]
    color_is_changing = (
        normalize_color_name(color_name) != normalize_color_name(product.color_name)
        or normalize_color_hex(requested_hex or "808080") != (product.color_hex or "808080")
        or requested_mode != product.color_mode
        or [normalize_color_hex(value) for value in comparison_palette] != current_palette
    )
    if color_is_changing and await _filaments_have_recorded_use(session, [product.id]):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "filament_color_locked",
            "Filament color cannot change after recorded use",
        )
    color = await _remember_color(
        session,
        color_name=color_name,
        color_hex=requested_hex,
        color_mode=requested_mode,
        color_hexes=requested_palette,
        actor_id=operator.id,
        correlation_id=request.state.correlation_id,
        exclude_product_id=product.id,
    )
    product.color_name = color.name
    product.color_hex = color.color_hex
    product.color_mode = color.color_mode
    product.color_hexes = color.color_hexes
    if "vendor_id" in payload.model_fields_set:
        product.vendor_id = payload.vendor_id
    for field in (
        "material_type",
        "diameter_mm",
        "density_g_cm3",
        "nominal_net_mass_g",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(product, field, value.strip() if isinstance(value, str) else value)
    if "tolerance_mm" in payload.model_fields_set:
        product.tolerance_mm = payload.tolerance_mm
    for field in ("filler", "finish", "product_name", "notes"):
        if field in payload.model_fields_set:
            value = getattr(payload, field)
            setattr(product, field, value.strip() or None if isinstance(value, str) else value)
    if "archived" in payload.model_fields_set and payload.archived is not None:
        product.archived = payload.archived

    created_profiles: list[MaterialProfile] = []
    density_changed = "density_g_cm3" in payload.model_fields_set
    if density_changed or (target_revision is not None and target_template is not None):
        current_profiles = await _current_product_profiles(session, product.id, lock=True)
        target_scope = (
            (target_template.printer_id, target_template.nozzle_diameter_mm)
            if target_template is not None
            else None
        )
        matched_target_scope = False
        for current_profile in current_profiles:
            scope = (current_profile.printer_id, current_profile.nozzle_diameter_mm)
            rebasing_scope = target_scope == scope and target_revision is not None
            matched_target_scope = matched_target_scope or rebasing_scope
            if not density_changed and not rebasing_scope:
                continue
            base_revision = (
                target_revision
                if rebasing_scope
                else await session.get(
                    MaterialTemplateRevision,
                    current_profile.base_template_revision_id,
                )
            )
            if base_revision is None:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "profile_template_missing",
                    "The current print-settings template is unavailable",
                )
            if not density_changed and current_profile.base_template_revision_id == base_revision.id:
                continue
            overrides = dict(current_profile.setting_overrides or {})
            if density_changed:
                template_density = Decimal(str(base_revision.settings["filament_density_g_cm3"]))
                if product.density_g_cm3 == template_density:
                    overrides.pop("filament_density_g_cm3", None)
                else:
                    overrides["filament_density_g_cm3"] = format(product.density_g_cm3, "f")
            resolved = resolve_profile_settings(base_revision.settings, overrides)
            created_profiles.append(
                await create_published_profile_snapshot(
                    session,
                    filament_product_id=product.id,
                    printer_id=current_profile.printer_id,
                    nozzle_diameter_mm=current_profile.nozzle_diameter_mm,
                    base_revision=base_revision,
                    settings=resolved,
                    setting_overrides=overrides,
                )
            )
        if target_revision is not None and target_template is not None:
            if not matched_target_scope:
                raise ApiError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "template_scope_mismatch",
                    "The filament does not have print settings for that printer and nozzle",
                )
            product.source_template_revision_id = target_revision.id
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
            "color_mode": product.color_mode,
            "color_hexes": product.color_hexes,
            "record_version": product.record_version,
            "source_template_revision_id": (
                str(product.source_template_revision_id)
                if product.source_template_revision_id is not None
                else None
            ),
            "material_profile_ids": [str(profile.id) for profile in created_profiles],
            "archived": product.archived,
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
    if created_profiles or "archived" in payload.model_fields_set:
        await queue_managed_cura_library(session, requested_by=operator.id)
    # Build and validate the response inside the transaction so a serialization
    # failure rolls the edit back instead of leaving the catalog unreadable.
    await session.flush()
    await session.refresh(product, attribute_names=["vendor"])
    response = filament_response(
        product,
        color_editable=not await _filaments_have_recorded_use(session, [product.id]),
    )
    await session.commit()
    return response


@router.delete("/filaments/{filament_id}")
async def delete_or_archive_filament(
    filament_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Delete an unused setup mistake, or archive a product with retained history."""

    product = await session.scalar(
        select(FilamentProduct).where(FilamentProduct.id == filament_id).with_for_update()
    )
    if product is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_filament", "Filament not found")
    active_spool = await session.scalar(
        select(Spool.id).where(
            Spool.filament_product_id == product.id,
            Spool.active_printer_id.is_not(None),
        )
    )
    if active_spool is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "active_filament_cannot_archive",
            "Unload this filament's active spool before deleting or archiving it",
        )

    profile_ids = list(
        await session.scalars(
            select(MaterialProfile.id).where(MaterialProfile.filament_product_id == product.id)
        )
    )
    dependency_checks = [
        select(func.count(Spool.id)).where(Spool.filament_product_id == product.id),
        select(func.count(CalibrationSession.id)).where(CalibrationSession.filament_product_id == product.id),
        select(func.count(PrintJob.id)).where(PrintJob.filament_product_id == product.id),
        select(func.count(PrintMaterialSegment.id)).where(
            PrintMaterialSegment.filament_product_id == product.id
        ),
    ]
    if profile_ids:
        dependency_checks.append(
            select(func.count(CuraDeployment.id)).where(CuraDeployment.material_profile_id.in_(profile_ids))
        )
    has_dependencies = False
    for dependency_query in dependency_checks:
        if (await session.scalar(dependency_query) or 0) > 0:
            has_dependencies = True
            break
    if has_dependencies:
        if not product.archived:
            product.archived = True
            product.record_version += 1
            add_outbox_job(
                session,
                job_type="spoolman.filament.upsert",
                idempotency_key=f"filament:{product.id}:archive:v{product.record_version}",
                aggregate_type="filament_product",
                aggregate_id=product.id,
                aggregate_version=product.record_version,
                payload={"filament_product_id": str(product.id)},
            )
            await queue_managed_cura_library(session, requested_by=operator.id)
        add_audit_event(
            session,
            actor_id=operator.id,
            source="web",
            action="filament.archive",
            object_type="filament_product",
            object_id=product.id,
            before={"archived": False},
            after={"archived": True, "dependent_history_retained": True},
            correlation_id=request.state.correlation_id,
        )
        await session.commit()
        return {"disposition": "archived"}

    projection = await _projection_state(session, "filament_product", product.id)
    remote_id = projection.remote_id if projection is not None else None
    add_outbox_job(
        session,
        job_type="spoolman.filament.delete",
        idempotency_key=f"filament:{product.id}:delete",
        aggregate_type="filament_product",
        aggregate_id=product.id,
        aggregate_version=product.record_version,
        payload={"remote_id": remote_id},
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="filament.delete",
        object_type="filament_product",
        object_id=product.id,
        before={"material_type": product.material_type, "color_name": product.color_name},
        after=None,
        correlation_id=request.state.correlation_id,
    )
    if profile_ids:
        await session.execute(delete(MaterialProfile).where(MaterialProfile.id.in_(profile_ids)))
    await session.delete(product)
    await session.flush()
    await queue_managed_cura_library(session, requested_by=operator.id)
    await session.commit()
    return {"disposition": "deleted"}


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
                FilamentProduct.filler.ilike(term),
                FilamentProduct.finish.ilike(term),
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
    spools = list(result.unique().scalars())
    print_counts = await completed_spool_print_counts(session, [spool.id for spool in spools])
    return Page(
        items=[
            spool_response(spool, completed_print_count=print_counts.get(spool.id, 0)).model_dump(mode="json")
            for spool in spools
        ],
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
    resolved_tare = payload.tare_mass_g or Decimal("0")
    effective = payload.nominal_net_mass_g
    confidence = "estimated"
    spool_status = SpoolStatus.NEEDS_WEIGHING
    initial_measured_at: datetime | None = None
    if payload.initial_gross_mass_g is not None:
        if payload.tare_mass_g is None or payload.tare_mass_g == 0:
            resolved_tare = payload.initial_gross_mass_g - payload.nominal_net_mass_g
            if resolved_tare < 0:
                raise ApiError(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "invalid_weight",
                    "Full spool weight cannot be less than the filament amount",
                )
        try:
            calculation = calculate_measurement(
                gross_mass_g=payload.initial_gross_mass_g,
                tare_mass_g=resolved_tare,
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
        initial_measured_at = datetime.now(UTC)

    spool = Spool(
        spool_code=payload.spool_code.upper(),
        filament_product_id=payload.filament_product_id,
        nominal_net_mass_g=payload.nominal_net_mass_g,
        tare_mass_g=resolved_tare,
        remaining_mass_expected_g=effective,
        remaining_mass_measured_g=measured,
        remaining_mass_effective_g=effective,
        weight_confidence=confidence,
        status=spool_status,
        last_measurement_at=initial_measured_at,
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
    if payload.initial_gross_mass_g is not None and measured is not None:
        assert initial_measured_at is not None
        session.add(
            SpoolMeasurement(
                spool_id=spool.id,
                source=MeasurementSource.MANUAL,
                status=MeasurementStatus.ACCEPTED,
                gross_mass_g=payload.initial_gross_mass_g,
                tare_mass_g=resolved_tare,
                net_mass_g=measured,
                expected_before_g=payload.nominal_net_mass_g,
                variance_g=measured - payload.nominal_net_mass_g,
                confidence="measured",
                requires_confirmation=False,
                confirmed=True,
                idempotency_key=f"initial-{spool.id}",
                operator_id=operator.id,
                measured_at=initial_measured_at,
                created_at=initial_measured_at,
                notes="Initial full-spool measurement",
            )
        )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="spool.create",
        object_type="spool",
        object_id=spool.id,
        before=None,
        after={
            "spool_code": spool.spool_code,
            "remaining_mass_effective_g": str(effective),
            "tare_mass_g": str(resolved_tare),
            "tare_inferred": payload.initial_gross_mass_g is not None
            and (payload.tare_mass_g is None or payload.tare_mass_g == 0),
        },
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
    await queue_managed_cura_library(session, requested_by=operator.id)
    await session.commit()
    spool.filament_product = product
    return await spool_response_with_statistics(session, spool)


@router.get("/spools/{spool_id}", response_model=SpoolResponse)
async def get_spool(spool_id: UUID, _: Viewer, session: DatabaseSession) -> SpoolResponse:
    """Return one physical spool by UUID."""

    return await spool_response_with_statistics(session, await _get_spool(session, spool_id))


@router.get("/spools/by-code/{spool_code}", response_model=SpoolResponse)
async def get_spool_by_code(spool_code: str, _: Viewer, session: DatabaseSession) -> SpoolResponse:
    """Resolve a scanned or typed immutable human spool code."""

    return await spool_response_with_statistics(session, await _get_spool(session, spool_code))


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
    if payload.spool_code is not None:
        existing_code = await session.scalar(
            select(Spool.id).where(
                func.lower(Spool.spool_code) == payload.spool_code.casefold(),
                Spool.id != spool.id,
            )
        )
        if existing_code is not None:
            raise ApiError(status.HTTP_409_CONFLICT, "spool_code_exists", "Spool code already exists")
    identity_changes = (
        payload.spool_code is not None and payload.spool_code.casefold() != spool.spool_code.casefold()
    ) or (
        payload.filament_product_id is not None and payload.filament_product_id != spool.filament_product_id
    )
    if identity_changes and await _spool_has_retained_history(session, spool.id):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "spool_identity_locked",
            "Spool code and filament can change only before measurements, use, or print history",
        )
    target_product: FilamentProduct | None = None
    if payload.filament_product_id is not None:
        target_product = await session.get(FilamentProduct, payload.filament_product_id)
        if target_product is None or target_product.archived:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "unknown_filament",
                "Select an active filament product",
            )
    proposed_nominal = payload.nominal_net_mass_g or spool.nominal_net_mass_g
    proposed_remaining = (
        payload.remaining_mass_g
        if "remaining_mass_g" in payload.model_fields_set and payload.remaining_mass_g is not None
        else spool.remaining_mass_effective_g
    )
    if proposed_remaining > proposed_nominal:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "remaining_above_capacity",
            "Remaining filament cannot exceed this spool's filament capacity",
        )
    if payload.archived is True and spool.active_printer_id is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "active_spool_cannot_archive",
            "Unload the spool from the printer before archiving it",
        )

    editable_fields = payload.model_fields_set - {"expected_version", "remaining_mass_g"}
    before = {field: getattr(spool, field) for field in editable_fields}
    if "remaining_mass_g" in payload.model_fields_set:
        before["remaining_mass_g"] = spool.remaining_mass_effective_g
    for field in editable_fields:
        value = getattr(payload, field)
        if field == "spool_code" and value is not None:
            value = value.upper()
        if field in {"purchase_source", "notes"} and isinstance(value, str):
            value = value.strip() or None
        setattr(spool, field, value)
    if target_product is not None:
        spool.filament_product = target_product
    usage_correction = (
        "remaining_mass_g" in payload.model_fields_set
        and payload.remaining_mass_g is not None
        and payload.remaining_mass_g != spool.remaining_mass_effective_g
    )
    if usage_correction:
        assert payload.remaining_mass_g is not None
        occurred_at = datetime.now(UTC)
        delta = payload.remaining_mass_g - spool.remaining_mass_effective_g
        session.add(
            SpoolUsageEvent(
                spool_id=spool.id,
                source="operator_correction",
                printer_id=spool.active_printer_id,
                mass_delta_g=delta,
                idempotency_key=f"correction:{request.state.correlation_id}"[:128],
                occurred_at=occurred_at,
                created_at=occurred_at,
            )
        )
        spool.remaining_mass_expected_g = payload.remaining_mass_g
        spool.remaining_mass_measured_g = None
        spool.remaining_mass_effective_g = payload.remaining_mass_g
        spool.weight_confidence = "operator_corrected"
        spool.last_usage_event_at = occurred_at
    if "location" in payload.model_fields_set:
        # A browser edit, including clearing the field, permanently establishes
        # Filament Manager as the owner instead of re-importing a remote value.
        spool.location_authoritative = True
    if spool.archived:
        spool.status = SpoolStatus.ARCHIVED
    elif spool.remaining_mass_effective_g <= 0:
        spool.status = SpoolStatus.EMPTY
    elif spool.remaining_mass_effective_g / spool.nominal_net_mass_g * Decimal("100") < Decimal(
        str(get_settings().sync.low_spool_threshold_percent)
    ):
        spool.status = SpoolStatus.LOW
    else:
        spool.status = SpoolStatus.IN_STOCK
    spool.record_version += 1
    after = {
        field: (spool.remaining_mass_effective_g if field == "remaining_mass_g" else getattr(spool, field))
        for field in before
    }
    cura_cost_changed = any(
        before.get(field) != after.get(field)
        for field in {
            "filament_product_id",
            "nominal_net_mass_g",
            "purchase_cost",
            "currency",
            "archived",
        }
        if field in before
    )
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
    if usage_correction and spool.spoolman_id is not None:
        add_outbox_job(
            session,
            job_type="spoolman.spool.adjust_weight",
            idempotency_key=f"spool:{spool.id}:correction:v{spool.record_version}",
            aggregate_type="spool",
            aggregate_id=spool.id,
            aggregate_version=spool.record_version,
            payload={"spool_id": str(spool.id)},
        )
    if cura_cost_changed:
        await queue_managed_cura_library(session, requested_by=operator.id)
    await session.commit()
    return await spool_response_with_statistics(session, spool)


@router.delete("/spools/{spool_id}")
async def delete_or_archive_spool(
    spool_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Delete an unused setup mistake, or archive a spool with retained history."""

    spool = await _get_spool(session, spool_id, lock=True)
    if spool.active_printer_id is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "active_spool_cannot_archive",
            "Unload the spool from the printer before deleting or archiving it",
        )
    has_dependencies = await _spool_has_retained_history(session, spool.id)
    if has_dependencies:
        if not spool.archived:
            spool.archived = True
            spool.status = SpoolStatus.ARCHIVED
            spool.record_version += 1
            add_outbox_job(
                session,
                job_type="spoolman.spool.upsert",
                idempotency_key=f"spool:{spool.id}:archive:v{spool.record_version}",
                aggregate_type="spool",
                aggregate_id=spool.id,
                aggregate_version=spool.record_version,
                payload={"spool_id": str(spool.id)},
            )
        add_audit_event(
            session,
            actor_id=operator.id,
            source="web",
            action="spool.archive",
            object_type="spool",
            object_id=spool.id,
            before={"archived": False},
            after={"archived": True, "dependent_history_retained": True},
            correlation_id=request.state.correlation_id,
        )
        await queue_managed_cura_library(session, requested_by=operator.id)
        await session.commit()
        return {"disposition": "archived"}

    projection = await _projection_state(session, "spool", spool.id)
    remote_id = spool.spoolman_id or (
        int(projection.remote_id) if projection is not None and projection.remote_id else None
    )
    add_outbox_job(
        session,
        job_type="spoolman.spool.delete",
        idempotency_key=f"spool:{spool.id}:delete",
        aggregate_type="spool",
        aggregate_id=spool.id,
        aggregate_version=spool.record_version,
        payload={"remote_id": remote_id},
    )
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="spool.delete",
        object_type="spool",
        object_id=spool.id,
        before={"spool_code": spool.spool_code},
        after=None,
        correlation_id=request.state.correlation_id,
    )
    # The initial full-spool observation belongs to the removable setup record,
    # not retained operational history. Later measurements remain immutable and
    # force archival through the dependency check above.
    await session.execute(
        delete(SpoolMeasurement).where(
            SpoolMeasurement.spool_id == spool.id,
            SpoolMeasurement.idempotency_key == f"initial-{spool.id}",
        )
    )
    await session.delete(spool)
    await queue_filament_default_projection(
        session,
        product_id=spool.filament_product_id,
        source_key=f"spool:{spool.id}:delete",
    )
    await queue_managed_cura_library(session, requested_by=operator.id)
    await session.commit()
    return {"disposition": "deleted"}


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
    # A weighing can establish an unknown tare or empty the spool. Refresh its
    # metadata and shared product defaults as well as the explicit net correction.
    add_outbox_job(
        session,
        job_type="spoolman.spool.upsert",
        idempotency_key=f"measurement:{measurement.id}:metadata",
        aggregate_type="spool",
        aggregate_id=spool.id,
        aggregate_version=spool.record_version,
        payload={"spool_id": str(spool.id)},
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
async def request_spool_load(
    spool_id: UUID,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> dict[str, str]:
    """Request a confirmed physical spool change without pre-activating the spool."""

    spool = await _get_spool(session, spool_id)
    if spool.spoolman_id is None:
        raise ApiError(status.HTTP_409_CONFLICT, "spool_not_projected", "Project spool to Spoolman first")
    configured_printer_code = get_settings().moonraker.printers[0].id
    printer = await session.scalar(select(Printer).where(Printer.printer_code == configured_printer_code))
    if printer is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "printer_not_configured",
            "The configured Moonraker printer is not ready",
        )
    try:
        target = await spool_change_target(session, spool=spool, printer=printer)
    except SpoolPreflightError as exc:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "spool_change_not_ready",
            str(exc),
        ) from exc
    current = await session.scalar(select(Spool).where(Spool.active_printer_id == printer.id))
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="spool.change.request",
        object_type="spool",
        object_id=spool.id,
        before={
            "printer_id": str(printer.id),
            "active_spool_id": str(current.id) if current else None,
            "active_spoolman_id": current.spoolman_id if current else None,
        },
        after={
            "printer_id": str(printer.id),
            "requested_spool_id": str(spool.id),
            "requested_spoolman_id": target.spoolman_id,
        },
        correlation_id=request.state.correlation_id,
    )
    add_outbox_job(
        session,
        job_type="moonraker.spool_change.request",
        idempotency_key=f"spool-change:{spool.id}:{request.state.correlation_id}",
        aggregate_type="spool",
        aggregate_id=spool.id,
        aggregate_version=spool.record_version,
        payload={
            "spoolman_id": target.spoolman_id,
            "temperature_c": str(target.temperature_c),
            "prompt_label": target.prompt_label,
        },
    )
    await session.commit()
    return {"status": "change_queued"}


@router.get("/spools/{spool_id}/label")
async def spool_label(spool_id: UUID, _: Viewer, session: DatabaseSession) -> StreamingResponse:
    """Generate a stable spool URL QR code with the filament's colored spool icon."""

    spool = await _get_spool(session, spool_id)
    url = f"{str(get_settings().app.base_url).rstrip('/')}/spools/{spool.id}"
    product = spool.filament_product
    image = render_spool_label_png(
        url,
        color_mode=product.color_mode,
        color_hex=product.color_hex,
        color_hexes=product.color_hexes,
    )
    buffer = BytesIO(image)
    buffer.seek(0)
    headers = {"Content-Disposition": f'inline; filename="spool-{spool.spool_code}.png"'}
    return StreamingResponse(buffer, media_type="image/png", headers=headers)
