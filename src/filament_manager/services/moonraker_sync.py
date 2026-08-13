"""Apply supported Moonraker state to canonical printer and spool records."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.clients.moonraker import MoonrakerPrinterInformation
from filament_manager.models.inventory import Printer, Spool
from filament_manager.services.events import add_audit_event


@dataclass(frozen=True, slots=True)
class ActiveSpoolSyncResult:
    """Describe one canonical alignment with Moonraker's tracked spool ID."""

    printer_id: UUID
    spoolman_id: int | None
    active_spool_id: UUID | None
    changed: bool
    synchronized_at: datetime


def _bounded_text(value: object, limit: int) -> str | None:
    """Return one safe single-line external value without exposing arbitrary payloads."""

    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("\r", " ").replace("\n", " ")
    return normalized[:limit] or None


def _positive_decimal_text(value: object) -> str | None:
    """Convert a finite positive external number to JSON-safe decimal text."""

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return format(parsed, "f")


def _axis_values(value: object) -> tuple[Decimal, Decimal, Decimal] | None:
    """Read the documented toolhead xyz vector while ignoring an optional E value."""

    if not isinstance(value, list | tuple) or len(value) < 3:
        return None
    try:
        values = tuple(Decimal(str(item)) for item in value[:3])
    except (InvalidOperation, TypeError):
        return None
    if not all(item.is_finite() for item in values):
        return None
    return values  # type: ignore[return-value]


def discovered_printer_values(information: MoonrakerPrinterInformation) -> dict[str, object]:
    """Extract the allowed canonical subset from documented Moonraker responses."""

    configfile = information.object_status.get("configfile")
    settings = configfile.get("settings") if isinstance(configfile, dict) else None
    settings = settings if isinstance(settings, dict) else {}
    printer_settings = settings.get("printer")
    printer_settings = printer_settings if isinstance(printer_settings, dict) else {}
    extruder_settings = settings.get("extruder")
    extruder_settings = extruder_settings if isinstance(extruder_settings, dict) else {}
    kinematics = _bounded_text(printer_settings.get("kinematics"), 48)

    build_volume: dict[str, object] = {}
    toolhead = information.object_status.get("toolhead")
    toolhead = toolhead if isinstance(toolhead, dict) else {}
    axis_minimum = _axis_values(toolhead.get("axis_minimum"))
    axis_maximum = _axis_values(toolhead.get("axis_maximum"))
    if axis_minimum and axis_maximum:
        spans = tuple(maximum - minimum for minimum, maximum in zip(axis_minimum, axis_maximum, strict=True))
        if all(value > 0 for value in spans):
            build_volume = {
                "shape": "round" if kinematics == "delta" else "rectangular",
                "x_mm": format(spans[0], "f"),
                "y_mm": format(spans[1], "f"),
                "z_mm": format(spans[2], "f"),
            }
            if kinematics == "delta":
                build_volume["diameter_mm"] = format(min(spans[0], spans[1]), "f")

    values: dict[str, object] = {
        "kinematics": kinematics,
        "klipper_version": _bounded_text(information.printer_info.get("software_version"), 96),
        "moonraker_version": _bounded_text(information.server_info.get("moonraker_version"), 96),
        "host_name": _bounded_text(information.printer_info.get("hostname"), 255),
        "status": _bounded_text(information.printer_info.get("state"), 32) or "unknown",
    }
    nozzle = _positive_decimal_text(extruder_settings.get("nozzle_diameter"))
    if nozzle is not None:
        values["nozzle_diameter_mm"] = Decimal(nozzle)
    if build_volume:
        values["build_volume"] = build_volume
    return values


async def synchronize_printer_information(
    session: AsyncSession,
    *,
    printer_id: UUID,
    information: MoonrakerPrinterInformation,
    actor_id: UUID | None,
    correlation_id: str,
) -> Printer:
    """Refresh discovered printer fields while preserving manual hardware descriptions."""

    printer = await session.scalar(select(Printer).where(Printer.id == printer_id).with_for_update())
    if printer is None:
        raise LookupError("Printer not found")
    values = discovered_printer_values(information)
    before = {
        field: getattr(printer, field)
        for field in (
            "kinematics",
            "nozzle_diameter_mm",
            "klipper_version",
            "moonraker_version",
            "host_name",
            "build_volume",
            "status",
        )
    }
    for field, value in values.items():
        if value is not None:
            setattr(printer, field, value)
    synchronized_at = datetime.now(UTC)
    printer.last_seen_at = synchronized_at
    printer.last_info_sync_at = synchronized_at
    after = {field: getattr(printer, field) for field in before}
    changed = before != after
    if changed:
        printer.record_version += 1
    if changed or actor_id is not None:
        add_audit_event(
            session,
            actor_id=actor_id,
            source="moonraker",
            action="printer.synchronize_info",
            object_type="printer",
            object_id=printer.id,
            before={
                key: str(value) if isinstance(value, Decimal) else value for key, value in before.items()
            },
            after={key: str(value) if isinstance(value, Decimal) else value for key, value in after.items()},
            correlation_id=correlation_id,
        )
    await session.commit()
    return printer


async def synchronize_active_spool(
    session: AsyncSession,
    *,
    printer_id: UUID,
    spoolman_id: int | None,
    actor_id: UUID | None,
    correlation_id: str,
    commit: bool = True,
) -> ActiveSpoolSyncResult:
    """Make canonical active-spool state match Moonraker's current Spoolman selection."""

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:sync_key, 0))"),
        {"sync_key": f"moonraker:active-spool:{printer_id}"},
    )
    printer = await session.scalar(select(Printer).where(Printer.id == printer_id).with_for_update())
    if printer is None:
        raise LookupError("Printer not found")
    current_spools = list(
        await session.scalars(
            select(Spool).where(Spool.active_printer_id == printer.id).order_by(Spool.id).with_for_update()
        )
    )
    target = (
        await session.scalar(select(Spool).where(Spool.spoolman_id == spoolman_id).with_for_update())
        if spoolman_id is not None
        else None
    )
    previous_ids = [str(spool.id) for spool in current_spools]
    changed = any(spool.id != getattr(target, "id", None) for spool in current_spools)
    changed = changed or (target is not None and not current_spools)
    for spool in current_spools:
        if target is None or spool.id != target.id:
            spool.active_printer_id = None
            spool.record_version += 1
    if target is not None and target.active_printer_id != printer.id:
        target.active_printer_id = printer.id
        target.record_version += 1
    synchronized_at = datetime.now(UTC)
    if printer.status != "connected":
        printer.status = "connected"
        printer.record_version += 1
    printer.last_seen_at = synchronized_at
    if changed or actor_id is not None:
        add_audit_event(
            session,
            actor_id=actor_id,
            source="moonraker" if actor_id is None else "web",
            action="spool.active.synchronize",
            object_type="printer",
            object_id=printer.id,
            before={"active_spool_ids": previous_ids},
            after={
                "active_spool_id": str(target.id) if target is not None else None,
                "spoolman_id": spoolman_id,
                "spoolman_id_recognized": spoolman_id is None or target is not None,
            },
            correlation_id=correlation_id,
        )
    if commit:
        await session.commit()
    return ActiveSpoolSyncResult(
        printer_id=printer.id,
        spoolman_id=spoolman_id,
        active_spool_id=target.id if target is not None else None,
        changed=changed,
        synchronized_at=synchronized_at,
    )
