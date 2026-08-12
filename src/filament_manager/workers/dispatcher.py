"""Transactional outbox dispatcher and external projection handlers."""

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from filament_manager.clients.google_sheets import GoogleSheetsClient
from filament_manager.clients.moonraker import MoonrakerClient
from filament_manager.clients.spoolman import SpoolmanClient, SpoolmanNotFoundError
from filament_manager.config import get_settings
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
from filament_manager.services.events import add_audit_event, add_outbox_job

SPOOLMAN_FIELD_LOCK_KEY = 0x464D53504649454C
SPOOLMAN_FIELD_CACHE_SECONDS = 30
_spoolman_fields_ready_until = 0.0
_spoolman_fields_lock = asyncio.Lock()


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
        remote_remaining = Decimal(str(remote.get("remaining_weight", spool.remaining_mass_expected_g)))
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
    elif job.job_type == "spoolman.spool.upsert":
        spool = await session.scalar(
            select(Spool)
            .where(Spool.id == job.aggregate_id)
            .options(joinedload(Spool.filament_product).joinedload(FilamentProduct.vendor))
        )
        if spool:
            await _project_spool(session, spoolman, spool)
    elif job.job_type == "spoolman.spool.adjust_weight":
        spool = await session.get(Spool, job.aggregate_id)
        if spool and spool.spoolman_id:
            await spoolman.measure_spool(
                spool.spoolman_id, float(spool.remaining_mass_effective_g + spool.tare_mass_g)
            )
    elif job.job_type == "spoolman.reconcile.full":
        remote_spools = await _reconcile_spoolman(session, spoolman)
        # Persist printer-originated usage and release spool row locks before
        # the potentially longer full metadata convergence pass.
        await session.commit()
        await _converge_spoolman(session, spoolman, remote_spools)
    elif job.job_type == "moonraker.active_spool.set":
        spoolman_id = int(str(job.payload["spoolman_id"]))
        await MoonrakerClient(settings.moonraker.printers[0]).set_active_spool(spoolman_id)
    elif job.job_type == "moonraker.build_plate.select":
        printer_id = UUID(str(job.payload["printer_id"]))
        printer = await session.get(Printer, printer_id)
        config = next(
            (item for item in settings.moonraker.printers if printer and item.id == printer.printer_code),
            settings.moonraker.printers[0],
        )
        await MoonrakerClient(config).select_build_plate(str(job.payload["plate_code"]))
    elif job.job_type.startswith("google."):
        await _publish_inventory(session)
    else:
        raise ValueError(f"Unsupported outbox job type: {job.job_type}")


async def complete_job(session: AsyncSession, job: OutboxJob) -> None:
    """Mark a successfully dispatched job complete."""

    persisted = await session.get(OutboxJob, job.id, with_for_update=True)
    if persisted and persisted.status == JobStatus.RUNNING and persisted.locked_by == job.locked_by:
        persisted.status = JobStatus.COMPLETED
        persisted.completed_at = datetime.now(UTC)
        persisted.locked_by = None
        persisted.locked_at = None
    await session.commit()


async def fail_job(session: AsyncSession, job: OutboxJob, exc: Exception) -> None:
    """Schedule a bounded exponential retry without logging sensitive payloads."""

    persisted = await session.get(OutboxJob, job.id, with_for_update=True)
    if persisted is None or persisted.status != JobStatus.RUNNING or persisted.locked_by != job.locked_by:
        await session.rollback()
        return
    persisted.attempts += 1
    persisted.last_error_class = type(exc).__name__[:160]
    persisted.last_error_message = str(exc)[:500]
    persisted.locked_by = None
    persisted.locked_at = None
    if persisted.attempts >= persisted.max_attempts:
        persisted.status = JobStatus.DEAD
    else:
        persisted.status = JobStatus.PENDING
        delay_seconds = min(3600, 2 ** min(persisted.attempts, 10))
        persisted.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
    await session.commit()
