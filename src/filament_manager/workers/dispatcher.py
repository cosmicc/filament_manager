"""Transactional outbox dispatcher and external projection handlers."""

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import cast
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from filament_manager.clients.google_sheets import GoogleSheetsClient
from filament_manager.clients.moonraker import MoonrakerClient
from filament_manager.clients.spoolman import SpoolmanClient, SpoolmanNotFoundError
from filament_manager.config import PrinterConfig, get_settings
from filament_manager.domain.spoolman import decode_text_extra_field
from filament_manager.models.enums import JobStatus, SpoolStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    Printer,
    Spool,
    SpoolUsageEvent,
    Vendor,
)
from filament_manager.models.operations import OutboxJob, ProjectionState
from filament_manager.services.build_plate_sync import synchronize_build_plates
from filament_manager.services.events import add_audit_event, add_outbox_job
from filament_manager.services.moonraker_sync import (
    synchronize_active_spool,
    synchronize_printer_information,
)
from filament_manager.services.notifications import evaluate_operator_notifications
from filament_manager.services.print_history import (
    gcode_inspection_policy,
    synchronize_live_print,
    synchronize_print_history,
)
from filament_manager.services.seed import seed_configured_system
from filament_manager.services.spool_preflight import (
    build_spool_preflight_catalog,
    spool_change_target,
)

SPOOLMAN_FIELD_LOCK_KEY = 0x464D53504649454C
SPOOLMAN_FIELD_CACHE_SECONDS = 30
SPOOL_MASS_QUANTUM = Decimal("0.001")
_spoolman_fields_ready_until = 0.0
_spoolman_fields_lock = asyncio.Lock()
logger = structlog.get_logger()
RECONSTRUCTABLE_RECURRING_JOB_TYPES = frozenset(
    {
        "spoolman.reconcile.full",
        "moonraker.state.reconcile",
        "moonraker.printer_info.reconcile",
        "moonraker.print_history.reconcile",
        "notifications.evaluate",
        "google.publish.pending",
    }
)


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _remote_id(remote: dict[str, object]) -> int:
    """Return a validated integer ID from an external Spoolman record."""

    value = remote.get("id")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("Spoolman returned an invalid record ID")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("Spoolman returned an invalid record ID") from exc


def _remote_spool_location(remote: dict[str, object]) -> tuple[bool, str | None]:
    """Return a bounded normalized Spoolman location and whether it is valid."""

    value = remote.get("location")
    if value is None:
        return True, None
    if not isinstance(value, str):
        return False, None
    normalized = value.strip()
    if len(normalized) > 64:
        return False, None
    return True, normalized or None


def _projected_spool_location(value: str | None) -> str | None:
    """Bound a canonical location to Spoolman's documented 64 characters."""

    return value[:64] if value is not None else None


def _canonical_spool_mass(value: object) -> Decimal:
    """Normalize Spoolman mass to the canonical PostgreSQL NUMERIC scale."""

    try:
        mass = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Spoolman returned an invalid remaining weight") from exc
    if not mass.is_finite() or mass < 0:
        raise ValueError("Spoolman returned an invalid remaining weight")
    try:
        return mass.quantize(SPOOL_MASS_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Spoolman returned an invalid remaining weight") from exc


def _failure_class_summary(failures: list[Exception]) -> str:
    """Summarize bounded failure classes without retaining external response content."""

    counts: dict[str, int] = {}
    for failure in failures:
        name = type(failure).__name__[:80]
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{name} x{count}" if count > 1 else name for name, count in sorted(counts.items()))


def _managed_remote_ids(items: list[dict[str, object]], key: str) -> dict[UUID, int]:
    """Index valid managed UUIDs from one complete remote collection."""

    indexed: dict[UUID, int] = {}
    for item in items:
        extra = item.get("extra")
        if not isinstance(extra, dict):
            continue
        raw_uuid = decode_text_extra_field(extra.get(key))
        if raw_uuid is None:
            continue
        try:
            managed_uuid = UUID(raw_uuid)
            remote_id = _remote_id(item)
            if managed_uuid in indexed and indexed[managed_uuid] != remote_id:
                raise ValueError(f"Spoolman contains duplicate managed values for {key}")
            indexed[managed_uuid] = remote_id
        except ValueError:
            continue
    return indexed


async def claim_jobs(session: AsyncSession, worker_id: str, limit: int = 10) -> list[OutboxJob]:
    """Claim due or abandoned jobs without blocking other workers."""

    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=get_settings().sync.outbox_lock_timeout_seconds)
    result = await session.execute(
        select(OutboxJob)
        .where(
            or_(
                and_(OutboxJob.status == JobStatus.PENDING, OutboxJob.next_attempt_at <= now),
                and_(
                    OutboxJob.status == JobStatus.RUNNING,
                    or_(OutboxJob.locked_at.is_(None), OutboxJob.locked_at <= stale_before),
                ),
            )
        )
        .order_by(OutboxJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    jobs = list(result.scalars())
    for job in jobs:
        job.status = JobStatus.RUNNING
        job.locked_by = worker_id
        job.locked_at = now
    await session.commit()
    return jobs


async def _lock_projection(session: AsyncSession, system: str, object_type: str, object_id: UUID) -> None:
    """Serialize one external object across all in-process and Swarm workers."""

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:projection_key, 0))"),
        {"projection_key": f"{system}:{object_type}:{object_id}"},
    )


async def _ensure_spoolman_fields(session: AsyncSession, client: SpoolmanClient) -> None:
    """Serialize Spoolman's read-modify-write field provisioning across workers."""

    global _spoolman_fields_ready_until
    if time.monotonic() < _spoolman_fields_ready_until:
        return
    async with _spoolman_fields_lock:
        if time.monotonic() < _spoolman_fields_ready_until:
            return
        await session.execute(
            text("SELECT pg_advisory_lock(:lock_key)"),
            {"lock_key": SPOOLMAN_FIELD_LOCK_KEY},
        )
        try:
            await client.ensure_managed_fields()
            _spoolman_fields_ready_until = time.monotonic() + SPOOLMAN_FIELD_CACHE_SECONDS
        finally:
            await session.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": SPOOLMAN_FIELD_LOCK_KEY},
            )


async def _projection(
    session: AsyncSession, system: str, object_type: str, object_id: UUID
) -> ProjectionState | None:
    return cast(
        ProjectionState | None,
        await session.scalar(
            select(ProjectionState).where(
                ProjectionState.system == system,
                ProjectionState.object_type == object_type,
                ProjectionState.object_id == object_id,
            )
        ),
    )


async def _save_projection(
    session: AsyncSession,
    *,
    system: str,
    object_type: str,
    object_id: UUID,
    remote_id: str,
    remote_payload: object,
    version: int,
) -> None:
    state = await _projection(session, system, object_type, object_id)
    if state is None:
        state = ProjectionState(system=system, object_type=object_type, object_id=object_id)
        session.add(state)
    state.remote_id = remote_id
    state.remote_fingerprint = _fingerprint(remote_payload)
    state.acknowledged_version = version
    state.last_success_at = datetime.now(UTC)
    state.last_error = None


async def _seed_projection_remote_id(
    session: AsyncSession,
    *,
    object_type: str,
    object_id: UUID,
    remote_id: int,
) -> None:
    """Restore a local projection pointer discovered by managed remote UUID."""

    state = await _projection(session, "spoolman", object_type, object_id)
    if state is None:
        session.add(
            ProjectionState(
                system="spoolman",
                object_type=object_type,
                object_id=object_id,
                remote_id=str(remote_id),
            )
        )
    else:
        state.remote_id = str(remote_id)


async def _project_vendor(
    session: AsyncSession,
    client: SpoolmanClient,
    vendor: Vendor,
    *,
    allow_discovery: bool = True,
) -> int:
    await _lock_projection(session, "spoolman", "vendor", vendor.id)
    state = await _projection(session, "spoolman", "vendor", vendor.id)
    payload = {
        "name": vendor.name[:64],
        "comment": (vendor.notes or "")[:1024],
        "extra": {"filament_manager_vendor_uuid": str(vendor.id)},
    }
    remote: dict[str, object] | None = None
    if state and state.remote_id:
        try:
            remote = await client.update_vendor(int(state.remote_id), payload)
        except SpoolmanNotFoundError:
            state.remote_id = None
    if remote is None:
        if allow_discovery:
            remote = await client.find_managed_vendor(str(vendor.id))
            if remote is None:
                matches = await client.find_vendors(vendor.name)
                if matches:
                    remote = await client.update_vendor(int(matches[0]["id"]), payload)
                else:
                    remote = await client.create_vendor(payload)
            else:
                remote = await client.update_vendor(_remote_id(remote), payload)
        else:
            remote = await client.create_vendor(payload)
    remote_id = _remote_id(remote)
    await _save_projection(
        session,
        system="spoolman",
        object_type="vendor",
        object_id=vendor.id,
        remote_id=str(remote_id),
        remote_payload=remote,
        version=vendor.record_version,
    )
    return remote_id


async def _project_filament(
    session: AsyncSession,
    client: SpoolmanClient,
    product: FilamentProduct,
    vendor_remote_ids: dict[UUID, int] | None = None,
    *,
    allow_discovery: bool = True,
) -> int:
    vendor_id = None
    if product.vendor:
        if vendor_remote_ids is not None and product.vendor.id in vendor_remote_ids:
            vendor_id = vendor_remote_ids[product.vendor.id]
        else:
            vendor_id = await _project_vendor(
                session,
                client,
                product.vendor,
                allow_discovery=allow_discovery,
            )
            if vendor_remote_ids is not None:
                vendor_remote_ids[product.vendor.id] = vendor_id
    await _lock_projection(session, "spoolman", "filament_product", product.id)
    state = await _projection(session, "spoolman", "filament_product", product.id)
    payload = {
        "name": " ".join(filter(None, [product.product_name, product.color_name]))[:64],
        "vendor_id": vendor_id,
        "material": product.material_type[:64],
        "density": float(product.density_g_cm3),
        "diameter": float(product.diameter_mm),
        "weight": float(product.nominal_net_mass_g),
        "color_hex": product.color_hex,
        "comment": (product.notes or "")[:1024],
        "extra": {
            "filament_manager_product_uuid": str(product.id),
            "filler": product.filler or "",
            "finish": product.finish or "",
            "color_name": product.color_name,
            "display_palette": {
                "mode": product.color_mode,
                "colors": product.color_hexes,
            },
        },
    }
    remote: dict[str, object] | None = None
    if state and state.remote_id:
        try:
            remote = await client.update_filament(int(state.remote_id), payload)
        except SpoolmanNotFoundError:
            state.remote_id = None
    if remote is None:
        if allow_discovery:
            remote = await client.find_managed_filament(str(product.id))
            if remote is None:
                remote = await client.create_filament(payload)
            else:
                remote = await client.update_filament(_remote_id(remote), payload)
        else:
            remote = await client.create_filament(payload)
    remote_id = _remote_id(remote)
    await _save_projection(
        session,
        system="spoolman",
        object_type="filament_product",
        object_id=product.id,
        remote_id=str(remote_id),
        remote_payload=remote,
        version=product.record_version,
    )
    return remote_id


async def _project_spool(
    session: AsyncSession,
    client: SpoolmanClient,
    spool: Spool,
    filament_remote_ids: dict[UUID, int] | None = None,
    vendor_remote_ids: dict[UUID, int] | None = None,
    *,
    allow_discovery: bool = True,
) -> None:
    if filament_remote_ids is not None and spool.filament_product.id in filament_remote_ids:
        filament_id = filament_remote_ids[spool.filament_product.id]
    else:
        filament_id = await _project_filament(
            session,
            client,
            spool.filament_product,
            vendor_remote_ids,
            allow_discovery=allow_discovery,
        )
        if filament_remote_ids is not None:
            filament_remote_ids[spool.filament_product.id] = filament_id
    await _lock_projection(session, "spoolman", "spool", spool.id)
    payload = {
        "filament_id": filament_id,
        "price": float(spool.purchase_cost) if spool.purchase_cost is not None else None,
        "initial_weight": float(spool.nominal_net_mass_g),
        "spool_weight": float(spool.tare_mass_g),
        "remaining_weight": float(spool.remaining_mass_effective_g),
        "location": _projected_spool_location(spool.location),
        "comment": (spool.notes or "")[:1024],
        "archived": spool.archived,
        "extra": {
            "filament_manager_spool_uuid": str(spool.id),
            "sheet_spool_id": spool.spool_code,
        },
    }
    # Spoolman's remaining weight is printer-facing operational state. Ordinary
    # metadata convergence must not erase usage that has not yet been imported;
    # only creation and explicit measurement jobs write this field.
    update_payload = {key: value for key, value in payload.items() if key != "remaining_weight"}
    state = await _projection(session, "spoolman", "spool", spool.id)
    remote: dict[str, object] | None = None
    candidate_remote_id = spool.spoolman_id or (int(state.remote_id) if state and state.remote_id else None)
    if candidate_remote_id is not None:
        try:
            remote = await client.update_spool(candidate_remote_id, update_payload)
        except SpoolmanNotFoundError:
            spool.spoolman_id = None
            if state is not None:
                state.remote_id = None
    if remote is None:
        if allow_discovery:
            remote = await client.find_managed_spool(str(spool.id))
            if remote is None:
                remote = await client.create_spool(payload)
            else:
                remote = await client.update_spool(_remote_id(remote), update_payload)
        else:
            remote = await client.create_spool(payload)
    remote_id = _remote_id(remote)
    if spool.spoolman_id != remote_id:
        spool.spoolman_id = remote_id
        spool.record_version += 1
    await _save_projection(
        session,
        system="spoolman",
        object_type="spool",
        object_id=spool.id,
        remote_id=str(remote_id),
        remote_payload=remote,
        version=spool.record_version,
    )


async def _publish_inventory(session: AsyncSession) -> None:
    settings = get_settings()
    if not settings.google.enabled:
        return
    assert settings.google.spreadsheet_id
    result = await session.execute(
        select(Spool)
        .options(joinedload(Spool.filament_product).joinedload(FilamentProduct.vendor))
        .order_by(Spool.spool_code)
    )
    rows: list[list[object]] = [
        [
            "Spool ID",
            "Inventory Status",
            "Material Type",
            "Filler / Reinforcement",
            "Finish / Effect",
            "Color",
            "Manufacturer",
            "Product / Grade / Hardness",
            "Diameter (mm)",
            "Density (g/cm³)",
            "Nominal Weight (g)",
            "Tare (g)",
            "Remaining Filament (g)",
            "Location",
            "Spoolman ID",
            "Record UUID",
            "Record Version",
            "Updated At",
            "Published At",
        ]
    ]
    published_at = datetime.now(UTC).isoformat()
    for spool in result.unique().scalars():
        product = spool.filament_product
        rows.append(
            [
                spool.spool_code,
                spool.status.value,
                product.material_type,
                product.filler or "",
                product.finish or "",
                product.color_name,
                product.vendor.name if product.vendor else "",
                product.product_name or "",
                float(product.diameter_mm),
                float(product.density_g_cm3),
                float(spool.nominal_net_mass_g),
                float(spool.tare_mass_g),
                float(spool.remaining_mass_effective_g),
                spool.location or "",
                spool.spoolman_id or "",
                str(spool.id),
                spool.record_version,
                spool.updated_at.isoformat(),
                published_at,
            ]
        )
    client = GoogleSheetsClient(
        settings.google.spreadsheet_id,
        settings.google.service_account_file,
        settings.google.resolved_service_account_info(),
    )
    await client.write_values("Inventory!A1:S", rows)


async def _converge_spoolman(
    session: AsyncSession,
    client: SpoolmanClient,
    remote_spools: list[dict[str, object]] | None = None,
) -> None:
    """Project every canonical vendor, product, and spool to Spoolman."""

    vendor_remote_ids: dict[UUID, int] = {}
    filament_remote_ids: dict[UUID, int] = {}

    remote_vendors = await client.list_vendors()
    remote_filaments = await client.list_filaments()
    if remote_spools is None:
        remote_spools = await client.list_spools()
    known_vendor_ids = _managed_remote_ids(remote_vendors, "filament_manager_vendor_uuid")
    known_filament_ids = _managed_remote_ids(remote_filaments, "filament_manager_product_uuid")
    known_spool_ids = _managed_remote_ids(remote_spools, "filament_manager_spool_uuid")
    vendor_ids_by_name = {
        str(remote["name"]).strip().casefold(): _remote_id(remote)
        for remote in remote_vendors
        if isinstance(remote.get("name"), str)
    }

    vendors = list(await session.scalars(select(Vendor).order_by(Vendor.id)))
    for vendor in vendors:
        known_id = known_vendor_ids.get(vendor.id) or vendor_ids_by_name.get(vendor.name.casefold())
        if known_id is not None:
            await _seed_projection_remote_id(
                session,
                object_type="vendor",
                object_id=vendor.id,
                remote_id=known_id,
            )
        vendor_remote_ids[vendor.id] = await _project_vendor(
            session,
            client,
            vendor,
            allow_discovery=False,
        )

    product_result = await session.execute(
        select(FilamentProduct).options(joinedload(FilamentProduct.vendor)).order_by(FilamentProduct.id)
    )
    for product in product_result.unique().scalars():
        if known_id := known_filament_ids.get(product.id):
            await _seed_projection_remote_id(
                session,
                object_type="filament_product",
                object_id=product.id,
                remote_id=known_id,
            )
        filament_remote_ids[product.id] = await _project_filament(
            session,
            client,
            product,
            vendor_remote_ids,
            allow_discovery=False,
        )

    spool_result = await session.execute(
        select(Spool)
        .options(joinedload(Spool.filament_product).joinedload(FilamentProduct.vendor))
        .order_by(Spool.id)
    )
    for local_spool in spool_result.unique().scalars():
        if known_id := known_spool_ids.get(local_spool.id):
            await _seed_projection_remote_id(
                session,
                object_type="spool",
                object_id=local_spool.id,
                remote_id=known_id,
            )
            if local_spool.spoolman_id != known_id:
                local_spool.spoolman_id = known_id
                local_spool.record_version += 1
        await _project_spool(
            session,
            client,
            local_spool,
            filament_remote_ids,
            vendor_remote_ids,
            allow_discovery=False,
        )


async def _reconcile_spoolman(session: AsyncSession, client: SpoolmanClient) -> list[dict[str, object]]:
    """Import supported Spoolman usage and repair canonical location drift."""

    remotes = await client.list_spools()
    for remote in remotes:
        extra = remote.get("extra") or {}
        if not isinstance(extra, dict):
            continue
        raw_uuid = decode_text_extra_field(extra.get("filament_manager_spool_uuid"))
        if not raw_uuid:
            continue
        try:
            spool_id = UUID(str(raw_uuid))
        except ValueError:
            continue
        spool = await session.scalar(select(Spool).where(Spool.id == spool_id).with_for_update())
        if spool is None:
            continue
        location_is_valid, remote_location = _remote_spool_location(remote)
        if not spool.location_authoritative and location_is_valid and remote_location is not None:
            spool.location = remote_location
            spool.location_authoritative = True
            spool.record_version += 1
            add_audit_event(
                session,
                actor_id=None,
                source="spoolman",
                action="spool.location.import",
                object_type="spool",
                object_id=spool.id,
                before={"location": None},
                after={"location": spool.location},
                correlation_id=f"spoolman-location-{spool.id}",
            )
            add_outbox_job(
                session,
                job_type="google.inventory.publish",
                idempotency_key=f"spool:{spool.id}:google:location:v{spool.record_version}",
                aggregate_type="spool",
                aggregate_id=spool.id,
                aggregate_version=spool.record_version,
                payload={"spool_id": str(spool.id)},
            )
        elif spool.location_authoritative and (
            not location_is_valid or remote_location != _projected_spool_location(spool.location)
        ):
            # Spoolman is the operational projection. Repair remote edits or
            # invalid values from the canonical free-text location.
            updated_remote = await client.update_spool(
                int(remote["id"]),
                {"location": _projected_spool_location(spool.location)},
            )
            remote = {**remote, **updated_remote}
        remote_remaining = _canonical_spool_mass(
            remote.get("remaining_weight", spool.remaining_mass_expected_g)
        )
        delta = remote_remaining - spool.remaining_mass_expected_g
        if delta < 0:
            occurred_at = datetime.now(UTC)
            expected_before = spool.remaining_mass_expected_g
            effective_before = spool.remaining_mass_effective_g
            usage_key = (
                f"spoolman:{remote['id']}:{expected_before.normalize()}:{remote_remaining.normalize()}"
            )
            session.add(
                SpoolUsageEvent(
                    spool_id=spool.id,
                    source="spoolman",
                    printer_id=spool.active_printer_id,
                    mass_delta_g=delta,
                    idempotency_key=usage_key[:128],
                    occurred_at=occurred_at,
                    created_at=occurred_at,
                )
            )
            spool.remaining_mass_expected_g = remote_remaining
            spool.remaining_mass_effective_g = max(Decimal("0"), spool.remaining_mass_effective_g + delta)
            spool.last_usage_event_at = occurred_at
            spool.record_version += 1
            percent = spool.remaining_mass_effective_g / spool.nominal_net_mass_g * Decimal("100")
            spool.status = (
                SpoolStatus.EMPTY
                if spool.remaining_mass_effective_g <= 0
                else SpoolStatus.LOW
                if percent < Decimal(str(get_settings().sync.low_spool_threshold_percent))
                else SpoolStatus.IN_STOCK
            )
            add_audit_event(
                session,
                actor_id=None,
                source="spoolman",
                action="spool.usage.accept",
                object_type="spool",
                object_id=spool.id,
                before={
                    "expected_remaining_g": str(expected_before),
                    "effective_remaining_g": str(effective_before),
                },
                after={
                    "expected_remaining_g": str(spool.remaining_mass_expected_g),
                    "effective_remaining_g": str(spool.remaining_mass_effective_g),
                    "mass_delta_g": str(delta),
                },
                correlation_id=f"spoolman-reconcile-{spool.id}",
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
        await _save_projection(
            session,
            system="spoolman",
            object_type="spool",
            object_id=spool.id,
            remote_id=str(remote["id"]),
            remote_payload=remote,
            version=spool.record_version,
        )
    return remotes


async def _configured_printer_bindings(
    session: AsyncSession,
) -> list[tuple[Printer, PrinterConfig]]:
    """Seed and bind canonical printers to validated server-side configuration."""

    settings = get_settings()
    seeded = await seed_configured_system(session, settings)
    await session.commit()
    if seeded["printers"] or seeded["plates"] or seeded["templates"]:
        logger.info("configured_system_seeded", **seeded)
    result = await session.execute(
        select(Printer).where(Printer.printer_code.in_([item.id for item in settings.moonraker.printers]))
    )
    printers = {printer.printer_code: printer for printer in result.scalars()}
    bindings: list[tuple[Printer, PrinterConfig]] = []
    for configured in settings.moonraker.printers:
        printer = printers.get(configured.id)
        if printer is None:
            raise LookupError(f"Configured printer {configured.id} was not seeded")
        bindings.append((printer, configured))
    return bindings


async def _reconcile_moonraker_state(session: AsyncSession, job: OutboxJob) -> None:
    """Poll active spool and build-plate state without one surface blocking the other."""

    failures: list[tuple[str, Exception]] = []
    for printer, configured in await _configured_printer_bindings(session):
        client = MoonrakerClient(configured)
        active_result, mesh_result, preflight_result = await asyncio.gather(
            client.active_spool_id(),
            client.bed_mesh_state(),
            client.spool_preflight_state(),
            return_exceptions=True,
        )
        correlation_id = f"auto:{job.id}:state"
        if isinstance(active_result, BaseException):
            if not isinstance(active_result, Exception):
                raise active_result
            failures.append(("active spool read", active_result))
            logger.error(
                "moonraker_active_spool_sync_failed",
                printer_code=printer.printer_code,
                error_class=type(active_result).__name__,
                error=str(active_result),
                exc_info=(type(active_result), active_result, active_result.__traceback__),
            )
        else:
            effective_active_spool_id = active_result
            previous_preflight_status = printer.spool_preflight_status
            preflight_is_restoring = (
                not isinstance(preflight_result, BaseException)
                and preflight_result is not None
                and not preflight_result.restored
            )
            if isinstance(preflight_result, BaseException):
                printer.spool_preflight_status = "unavailable"
                printer.spool_preflight_message = (
                    "The Filament Manager spool macro state could not be read. "
                    "Verify the current macro include and Moonraker connection."
                )
                log_method = logger.warning if previous_preflight_status != "unavailable" else logger.debug
                log_method(
                    "moonraker_spool_preflight_macro_unavailable",
                    printer_code=printer.printer_code,
                    error_class=type(preflight_result).__name__,
                )
            elif preflight_result is None:
                printer.spool_preflight_status = "not_installed"
                printer.spool_preflight_message = (
                    "Install the current Filament Manager Klipper macros to enable guarded spool selection."
                )
                log_method = logger.warning if previous_preflight_status != "not_installed" else logger.debug
                log_method(
                    "moonraker_spool_preflight_macro_not_installed",
                    printer_code=printer.printer_code,
                )
            elif preflight_is_restoring:
                printer.spool_preflight_status = "restoring"
                printer.spool_preflight_message = "The persisted physical spool state is being restored."
                logger.info(
                    "moonraker_spool_preflight_state_restoring",
                    printer_code=printer.printer_code,
                )
            elif preflight_result.initialized and preflight_result.loaded_spool_id != active_result:
                # The persisted macro state advances only after a completed
                # physical unload/load routine. A direct non-null Spoolman
                # selection can become a guarded Fluidd target, but it never
                # becomes active canonical state before physical confirmation.
                effective_active_spool_id = preflight_result.loaded_spool_id
                if active_result is not None and preflight_result.phase in {
                    "idle",
                    "load_select",
                    "manual_select",
                }:
                    selected_spool = await session.scalar(
                        select(Spool).where(Spool.spoolman_id == active_result)
                    )
                    if selected_spool is None:
                        logger.warning(
                            "moonraker_spoolman_target_unrecognized",
                            printer_code=printer.printer_code,
                            reported_spoolman_id=active_result,
                        )
                    else:
                        try:
                            target = await spool_change_target(
                                session,
                                spool=selected_spool,
                                printer=printer,
                            )
                            await client.request_spoolman_target(
                                spoolman_id=target.spoolman_id,
                                temperature_c=target.temperature_c,
                                prompt_label=target.prompt_label,
                            )
                            logger.warning(
                                "moonraker_spoolman_target_prompted",
                                printer_code=printer.printer_code,
                                phase=preflight_result.phase,
                                target_spoolman_id=active_result,
                            )
                        except Exception as exc:
                            logger.warning(
                                "moonraker_spoolman_target_rejected",
                                printer_code=printer.printer_code,
                                reported_spoolman_id=active_result,
                                error_class=type(exc).__name__,
                                error=str(exc),
                            )
                try:
                    await client.set_active_spool(preflight_result.loaded_spool_id)
                    logger.warning(
                        "moonraker_active_spool_drift_repaired",
                        printer_code=printer.printer_code,
                        phase=preflight_result.phase,
                        reported_spoolman_id=active_result,
                        physically_loaded_spoolman_id=preflight_result.loaded_spool_id,
                    )
                except Exception as exc:
                    failures.append(("active spool drift repair", exc))
                    logger.exception(
                        "moonraker_active_spool_drift_repair_failed",
                        printer_code=printer.printer_code,
                        phase=preflight_result.phase,
                        error_class=type(exc).__name__,
                        error=str(exc),
                    )
            if not preflight_is_restoring:
                active_sync = await synchronize_active_spool(
                    session,
                    printer_id=printer.id,
                    spoolman_id=effective_active_spool_id,
                    actor_id=None,
                    correlation_id=correlation_id,
                )
                logger.info(
                    "moonraker_active_spool_synchronized",
                    printer_code=printer.printer_code,
                    spoolman_id=active_sync.spoolman_id,
                    active_spool_id=(
                        str(active_sync.active_spool_id) if active_sync.active_spool_id else None
                    ),
                    changed=active_sync.changed,
                )
                if not isinstance(preflight_result, BaseException) and preflight_result is not None:
                    try:
                        catalog = await build_spool_preflight_catalog(session, printer=printer)
                        inspection_policy = await gcode_inspection_policy(session)
                        if (
                            catalog.revision != preflight_result.catalog_revision
                            or inspection_policy != preflight_result.inspection_policy
                        ):
                            await client.synchronize_spool_preflight_catalog(
                                catalog, inspection_policy=inspection_policy
                            )
                            logger.info(
                                "moonraker_spool_preflight_catalog_synchronized",
                                printer_code=printer.printer_code,
                                revision=catalog.revision,
                                material_count=len(catalog.materials),
                                spool_count=len(catalog.temperatures),
                            )
                        if not preflight_result.initialized:
                            temperature_text = (
                                catalog.temperatures.get(str(effective_active_spool_id))
                                if effective_active_spool_id is not None
                                else None
                            )
                            await client.initialize_spool_preflight_state(
                                spoolman_id=effective_active_spool_id,
                                temperature_c=(Decimal(temperature_text) if temperature_text else None),
                            )
                            logger.info(
                                "moonraker_spool_preflight_state_initialized",
                                printer_code=printer.printer_code,
                                spoolman_id=effective_active_spool_id,
                            )
                        printer.spool_preflight_status = "healthy"
                        printer.spool_preflight_message = None
                        printer.last_spool_preflight_sync_at = datetime.now(UTC)
                    except Exception as exc:
                        # Catalog publication is an optional Klipper integration surface.
                        # Preserve the successful physical spool and build-plate state
                        # reconciliation, expose this failure in Diagnostics, and retry
                        # on the next normal poll instead of creating endless dead jobs.
                        printer.spool_preflight_status = "error"
                        printer.spool_preflight_message = (
                            "Spool catalog synchronization failed. Verify the current "
                            "Filament Manager macros and Klipper save_variables configuration."
                        )
                        log_method = logger.warning if previous_preflight_status != "error" else logger.debug
                        log_method(
                            "moonraker_spool_preflight_synchronization_failed",
                            printer_code=printer.printer_code,
                            error_class=type(exc).__name__,
                        )
        if isinstance(mesh_result, BaseException):
            if not isinstance(mesh_result, Exception):
                raise mesh_result
            failures.append(("build plate mesh", mesh_result))
            logger.error(
                "moonraker_build_plate_sync_failed",
                printer_code=printer.printer_code,
                error_class=type(mesh_result).__name__,
                error=str(mesh_result),
                exc_info=(type(mesh_result), mesh_result, mesh_result.__traceback__),
            )
        else:
            plate_sync = await synchronize_build_plates(
                session,
                printer_id=printer.id,
                mesh_state=mesh_result,
                actor_id=None,
                correlation_id=correlation_id,
            )
            logger.info(
                "moonraker_build_plates_synchronized",
                printer_code=printer.printer_code,
                discovered_count=len(plate_sync.discovered_codes),
                created_codes=plate_sync.created_codes,
                unavailable_codes=plate_sync.unavailable_codes,
                active_surface_code=plate_sync.active_surface_code,
            )
    if failures:
        summary = ", ".join(f"{operation} ({type(exc).__name__})" for operation, exc in failures[:6])
        raise RuntimeError(
            f"Moonraker state synchronization had {len(failures)} failure(s): {summary}"
        ) from failures[0][1]


async def _reconcile_moonraker_printer_information(session: AsyncSession, job: OutboxJob) -> None:
    """Refresh sanitized printer identity and hardware facts on a slower interval."""

    failures: list[Exception] = []
    for printer, configured in await _configured_printer_bindings(session):
        printer_code = printer.printer_code
        try:
            information = await MoonrakerClient(configured).printer_information()
            synchronized = await synchronize_printer_information(
                session,
                printer_id=printer.id,
                information=information,
                actor_id=None,
                correlation_id=f"auto:{job.id}:info",
            )
            logger.info(
                "moonraker_printer_information_synchronized",
                printer_code=printer_code,
                status=synchronized.status,
                klipper_version=synchronized.klipper_version,
                moonraker_version=synchronized.moonraker_version,
            )
        except Exception as exc:
            await session.rollback()
            failures.append(exc)
            logger.exception(
                "moonraker_printer_information_sync_failed",
                printer_code=printer_code,
                error_class=type(exc).__name__,
                error=str(exc),
            )
    if failures:
        raise RuntimeError(
            f"Moonraker printer-information synchronization had {len(failures)} failure(s): "
            f"{_failure_class_summary(failures)}"
        ) from failures[0]


async def _reconcile_moonraker_print_history(session: AsyncSession, job: OutboxJob) -> None:
    """Capture current exact state and import supported Moonraker history."""

    failures: list[Exception] = []
    for printer, configured in await _configured_printer_bindings(session):
        printer_id = printer.id
        printer_code = printer.printer_code
        client = MoonrakerClient(configured)
        print_result, preflight_result = await asyncio.gather(
            client.print_state(), client.spool_preflight_state(), return_exceptions=True
        )
        correlation_id = f"auto:{job.id}:prints"
        if isinstance(print_result, BaseException):
            if not isinstance(print_result, Exception):
                raise print_result
            failures.append(print_result)
            printer.status = "unavailable"
            printer.record_version += 1
            await session.commit()
            logger.error(
                "moonraker_print_state_sync_failed",
                printer_code=printer_code,
                error_class=type(print_result).__name__,
                error=str(print_result),
            )
        else:
            usable_preflight = preflight_result if not isinstance(preflight_result, BaseException) else None
            try:
                await synchronize_live_print(
                    session,
                    printer=printer,
                    client=client,
                    print_state=print_result,
                    preflight_state=usable_preflight,
                    correlation_id=correlation_id,
                )
            except Exception as exc:
                await session.rollback()
                failures.append(exc)
                logger.exception(
                    "moonraker_live_print_capture_failed",
                    printer_code=printer_code,
                    error_class=type(exc).__name__,
                    error=str(exc),
                )
                reloaded_printer = await session.get(Printer, printer_id)
                if reloaded_printer is None:
                    missing = LookupError("Moonraker print-history synchronization lost its printer")
                    failures.append(missing)
                    logger.error(
                        "moonraker_print_history_printer_missing",
                        printer_code=printer_code,
                    )
                    continue
                printer = reloaded_printer
        if not isinstance(print_result, BaseException) and print_result.state in {"printing", "paused"}:
            # Live capture already records the active job. Avoid fetching the
            # complete Moonraker history every five seconds during motion; the
            # next terminal-state pass imports the completed history promptly.
            logger.debug(
                "moonraker_terminal_history_deferred_while_printing",
                printer_code=printer_code,
                print_state=print_result.state,
            )
            continue
        try:
            imported = await synchronize_print_history(
                session,
                printer=printer,
                client=client,
                correlation_id=correlation_id,
            )
            logger.info(
                "moonraker_print_history_synchronized",
                printer_code=printer_code,
                reconciled_jobs=imported,
            )
        except Exception as exc:
            await session.rollback()
            failures.append(exc)
            logger.exception(
                "moonraker_print_history_sync_failed",
                printer_code=printer_code,
                error_class=type(exc).__name__,
                error=str(exc),
            )
    if failures:
        raise RuntimeError(
            f"Moonraker print-history synchronization had {len(failures)} failure(s): "
            f"{_failure_class_summary(failures)}"
        ) from failures[0]


async def dispatch_job(session: AsyncSession, job: OutboxJob) -> None:
    """Execute one claimed job with current canonical state."""

    settings = get_settings()
    spoolman = SpoolmanClient(settings.spoolman)
    if job.job_type.startswith("spoolman."):
        await _ensure_spoolman_fields(session, spoolman)
    if job.job_type == "spoolman.filament.upsert":
        product = await session.scalar(
            select(FilamentProduct)
            .where(FilamentProduct.id == job.aggregate_id)
            .options(joinedload(FilamentProduct.vendor))
        )
        if product:
            await _project_filament(session, spoolman, product)
    elif job.job_type == "spoolman.filament.delete":
        remote_id = job.payload.get("remote_id")
        if remote_id is not None:
            try:
                await spoolman.delete_filament(int(str(remote_id)))
            except SpoolmanNotFoundError:
                pass
        state = await _projection(session, "spoolman", "filament_product", job.aggregate_id)
        if state is not None:
            await session.delete(state)
    elif job.job_type == "spoolman.spool.upsert":
        spool = await session.scalar(
            select(Spool)
            .where(Spool.id == job.aggregate_id)
            .options(joinedload(Spool.filament_product).joinedload(FilamentProduct.vendor))
        )
        if spool:
            await _project_spool(session, spoolman, spool)
    elif job.job_type == "spoolman.spool.delete":
        remote_id = job.payload.get("remote_id")
        if remote_id is not None:
            try:
                await spoolman.delete_spool(int(str(remote_id)))
            except SpoolmanNotFoundError:
                pass
        state = await _projection(session, "spoolman", "spool", job.aggregate_id)
        if state is not None:
            await session.delete(state)
    elif job.job_type == "spoolman.spool.adjust_weight":
        spool = await session.get(Spool, job.aggregate_id)
        if spool and spool.spoolman_id:
            await spoolman.set_spool_remaining_weight(
                spool.spoolman_id, float(spool.remaining_mass_effective_g)
            )
    elif job.job_type == "spoolman.reconcile.full":
        remote_spools = await _reconcile_spoolman(session, spoolman)
        # Persist printer-originated usage and release spool row locks before
        # the potentially longer full metadata convergence pass.
        await session.commit()
        await _converge_spoolman(session, spoolman, remote_spools)
    elif job.job_type == "moonraker.state.reconcile":
        await _reconcile_moonraker_state(session, job)
    elif job.job_type == "moonraker.printer_info.reconcile":
        await _reconcile_moonraker_printer_information(session, job)
    elif job.job_type == "moonraker.print_history.reconcile":
        await _reconcile_moonraker_print_history(session, job)
    elif job.job_type == "notifications.evaluate":
        await evaluate_operator_notifications(session)
    elif job.job_type in {"moonraker.active_spool.set", "moonraker.spool_change.request"}:
        spool = await session.get(Spool, job.aggregate_id)
        if spool is None:
            raise LookupError("Spool change request references a missing spool")
        configured_printer = await session.scalar(
            select(Printer).where(Printer.printer_code == settings.moonraker.printers[0].id)
        )
        if configured_printer is None:
            raise LookupError("Configured Moonraker printer is not ready")
        target = await spool_change_target(
            session,
            spool=spool,
            printer=configured_printer,
        )
        await MoonrakerClient(settings.moonraker.printers[0]).request_spool_change(
            spoolman_id=target.spoolman_id,
            temperature_c=target.temperature_c,
            prompt_label=target.prompt_label,
        )
    elif job.job_type == "moonraker.build_plate.select":
        printer_id = UUID(str(job.payload["printer_id"]))
        printer = await session.get(Printer, printer_id)
        select_config = next(
            (item for item in settings.moonraker.printers if printer and item.id == printer.printer_code),
            settings.moonraker.printers[0],
        )
        await MoonrakerClient(select_config).select_build_plate(str(job.payload["plate_code"]))
    elif job.job_type == "moonraker.build_plate.clear":
        printer = await session.get(Printer, UUID(str(job.payload["printer_id"])))
        if printer is None:
            raise LookupError("Build-plate clear references a missing printer")
        clear_config = next(
            (item for item in settings.moonraker.printers if item.id == printer.printer_code),
            None,
        )
        if clear_config is None:
            raise LookupError("Build-plate clear references an unconfigured printer")
        await MoonrakerClient(clear_config).clear_build_plate()
    elif job.job_type == "moonraker.spool_unload.request":
        printer = await session.get(Printer, UUID(str(job.payload["printer_id"])))
        if printer is None:
            raise LookupError("Spool unload references a missing printer")
        unload_config = next(
            (item for item in settings.moonraker.printers if item.id == printer.printer_code),
            None,
        )
        if unload_config is None:
            raise LookupError("Spool unload references an unconfigured printer")
        await MoonrakerClient(unload_config).request_spool_unload()
    elif job.job_type.startswith("google."):
        await _publish_inventory(session)
    else:
        raise ValueError(f"Unsupported outbox job type: {job.job_type}")


async def complete_job(session: AsyncSession, job: OutboxJob) -> None:
    """Mark a successfully dispatched job complete."""

    persisted = await session.get(OutboxJob, job.id, with_for_update=True)
    if persisted and persisted.status == JobStatus.RUNNING and persisted.locked_by == job.locked_by:
        completed_at = datetime.now(UTC)
        persisted.status = JobStatus.COMPLETED
        persisted.completed_at = completed_at
        persisted.locked_by = None
        persisted.locked_at = None
        if persisted.job_type in RECONSTRUCTABLE_RECURRING_JOB_TYPES:
            await session.execute(
                update(OutboxJob)
                .where(
                    OutboxJob.id != persisted.id,
                    OutboxJob.job_type == persisted.job_type,
                    OutboxJob.status.in_((JobStatus.FAILED, JobStatus.DEAD)),
                )
                .values(status=JobStatus.SUPERSEDED, completed_at=completed_at)
            )
        else:
            # A newer successful projection of the same canonical object makes
            # older failed versions historical rather than actionable debt.
            await session.execute(
                update(OutboxJob)
                .where(
                    OutboxJob.id != persisted.id,
                    OutboxJob.job_type == persisted.job_type,
                    OutboxJob.aggregate_type == persisted.aggregate_type,
                    OutboxJob.aggregate_id == persisted.aggregate_id,
                    OutboxJob.aggregate_version <= persisted.aggregate_version,
                    OutboxJob.status == JobStatus.DEAD,
                )
                .values(status=JobStatus.SUPERSEDED, completed_at=completed_at)
            )
        if persisted.job_type == "spoolman.reconcile.full":
            # Full convergence reprojects the current canonical vendor,
            # filament, and spool metadata. Earlier granular upsert failures
            # are therefore proven obsolete, while deletes and explicit weight
            # adjustments remain actionable until they succeed themselves.
            await session.execute(
                update(OutboxJob)
                .where(
                    OutboxJob.status == JobStatus.DEAD,
                    OutboxJob.job_type.in_(
                        (
                            "spoolman.vendor.upsert",
                            "spoolman.filament.upsert",
                            "spoolman.spool.upsert",
                        )
                    ),
                )
                .values(status=JobStatus.SUPERSEDED, completed_at=completed_at)
            )
    await session.commit()


async def fail_job(session: AsyncSession, job: OutboxJob, exc: Exception) -> JobStatus | None:
    """Schedule a bounded retry and return the persisted state for safe reporting."""

    persisted = await session.get(OutboxJob, job.id, with_for_update=True)
    if persisted is None or persisted.status != JobStatus.RUNNING or persisted.locked_by != job.locked_by:
        await session.rollback()
        return None
    persisted.attempts += 1
    persisted.last_error_class = type(exc).__name__[:160]
    persisted.last_error_message = str(exc)[:500]
    failure_time = datetime.now(UTC)
    persisted.last_error_at = failure_time
    persisted.locked_by = None
    persisted.locked_at = None
    if persisted.attempts >= persisted.max_attempts:
        persisted.status = JobStatus.DEAD
    else:
        persisted.status = JobStatus.PENDING
        delay_seconds = min(3600, 2 ** min(persisted.attempts, 10))
        settings = get_settings()
        periodic_retry_caps = {
            "moonraker.state.reconcile": settings.sync.moonraker_state_interval_seconds,
            "moonraker.print_history.reconcile": settings.sync.moonraker_print_interval_seconds,
            "moonraker.printer_info.reconcile": settings.sync.moonraker_info_interval_seconds,
            "spoolman.reconcile.full": settings.spoolman.full_reconcile_interval_minutes * 60,
            "notifications.evaluate": 60,
        }
        if settings.google.enabled:
            periodic_retry_caps["google.publish.pending"] = settings.google.publish_interval_seconds
        retry_cap = periodic_retry_caps.get(persisted.job_type)
        if retry_cap is not None:
            delay_seconds = min(delay_seconds, retry_cap)
        persisted.next_attempt_at = failure_time + timedelta(seconds=delay_seconds)
    await session.commit()
    return persisted.status
