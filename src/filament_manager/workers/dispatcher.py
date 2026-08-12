"""Transactional outbox dispatcher and external projection handlers."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from filament_manager.clients.google_sheets import GoogleSheetsClient
from filament_manager.clients.moonraker import MoonrakerClient
from filament_manager.clients.spoolman import SpoolmanClient
from filament_manager.config import get_settings
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


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _remote_spool_location(remote: dict[str, object]) -> tuple[bool, str | None]:
    """Return a bounded normalized Spoolman location and whether it is valid."""

    value = remote.get("location")
    if value is None:
        return True, None
    if not isinstance(value, str):
        return False, None
    normalized = value.strip()
    if len(normalized) > 160:
        return False, None
    return True, normalized or None


async def claim_jobs(session: AsyncSession, worker_id: str, limit: int = 10) -> list[OutboxJob]:
    """Claim due jobs without blocking other worker processes."""

    now = datetime.now(UTC)
    result = await session.execute(
        select(OutboxJob)
        .where(OutboxJob.status == JobStatus.PENDING, OutboxJob.next_attempt_at <= now)
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


async def _project_vendor(session: AsyncSession, client: SpoolmanClient, vendor: Vendor) -> int:
    state = await _projection(session, "spoolman", "vendor", vendor.id)
    payload = {
        "name": vendor.name[:64],
        "comment": vendor.notes or "",
        "extra": {"filament_manager_vendor_uuid": str(vendor.id)},
    }
    if state and state.remote_id:
        remote = await client.update_vendor(int(state.remote_id), payload)
    else:
        matches = await client.find_vendors(vendor.name)
        remote = matches[0] if matches else await client.create_vendor(payload)
        if matches:
            remote = await client.update_vendor(int(remote["id"]), payload)
    await _save_projection(
        session,
        system="spoolman",
        object_type="vendor",
        object_id=vendor.id,
        remote_id=str(remote["id"]),
        remote_payload=remote,
        version=vendor.record_version,
    )
    return int(remote["id"])


async def _project_filament(session: AsyncSession, client: SpoolmanClient, product: FilamentProduct) -> int:
    vendor_id = None
    if product.vendor:
        vendor_id = await _project_vendor(session, client, product.vendor)
    state = await _projection(session, "spoolman", "filament_product", product.id)
    payload = {
        "name": " ".join(filter(None, [product.product_name, product.color_name]))[:128],
        "vendor_id": vendor_id,
        "material": product.material_type,
        "density": float(product.density_g_cm3),
        "diameter": float(product.diameter_mm),
        "weight": float(product.nominal_net_mass_g),
        "color_hex": product.color_hex,
        "comment": product.notes or "",
        "extra": {
            "filament_manager_product_uuid": str(product.id),
            "filler": product.filler or "",
            "finish": product.finish or "",
            "color_name": product.color_name,
        },
    }
    if state and state.remote_id:
        remote = await client.update_filament(int(state.remote_id), payload)
    else:
        remote = await client.create_filament(payload)
    await _save_projection(
        session,
        system="spoolman",
        object_type="filament_product",
        object_id=product.id,
        remote_id=str(remote["id"]),
        remote_payload=remote,
        version=product.record_version,
    )
    return int(remote["id"])


async def _project_spool(session: AsyncSession, client: SpoolmanClient, spool: Spool) -> None:
    filament_id = await _project_filament(session, client, spool.filament_product)
    payload = {
        "filament_id": filament_id,
        "price": float(spool.purchase_cost) if spool.purchase_cost is not None else None,
        "initial_weight": float(spool.nominal_net_mass_g),
        "spool_weight": float(spool.tare_mass_g),
        "remaining_weight": float(spool.remaining_mass_effective_g),
        "location": spool.location,
        "comment": spool.notes or "",
        "archived": spool.archived,
        "extra": {
            "filament_manager_spool_uuid": str(spool.id),
            "sheet_spool_id": spool.spool_code,
        },
    }
    if spool.spoolman_id:
        remote = await client.update_spool(spool.spoolman_id, payload)
    else:
        remote = await client.create_spool(payload)
        spool.spoolman_id = int(remote["id"])
        spool.record_version += 1
    await _save_projection(
        session,
        system="spoolman",
        object_type="spool",
        object_id=spool.id,
        remote_id=str(remote["id"]),
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


async def _reconcile_spoolman(session: AsyncSession, client: SpoolmanClient) -> None:
    remotes = await client.list_spools()
    for remote in remotes:
        extra = remote.get("extra") or {}
        raw_uuid = extra.get("filament_manager_spool_uuid")
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
        elif spool.location_authoritative and (not location_is_valid or remote_location != spool.location):
            # Spoolman is the operational projection. Repair remote edits or
            # invalid values from the canonical free-text location.
            updated_remote = await client.update_spool(int(remote["id"]), {"location": spool.location})
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


async def dispatch_job(session: AsyncSession, job: OutboxJob) -> None:
    """Execute one claimed job with current canonical state."""

    settings = get_settings()
    spoolman = SpoolmanClient(settings.spoolman)
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
        await _reconcile_spoolman(session, spoolman)
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
    if persisted:
        persisted.status = JobStatus.COMPLETED
        persisted.completed_at = datetime.now(UTC)
        persisted.locked_by = None
        persisted.locked_at = None
    await session.commit()


async def fail_job(session: AsyncSession, job: OutboxJob, exc: Exception) -> None:
    """Schedule a bounded exponential retry without logging sensitive payloads."""

    persisted = await session.get(OutboxJob, job.id, with_for_update=True)
    if persisted is None:
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
