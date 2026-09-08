"""Resolve current printer connections without caching secrets across edits."""

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.config import PrinterConfig, Settings, get_settings
from filament_manager.models.inventory import Printer
from filament_manager.services.credentials import decrypt_credential


async def configured_printers(session: AsyncSession, settings: Settings | None = None) -> list[PrinterConfig]:
    """Overlay explicit database ownership over backward-compatible deployment seeds.

    Disabled managed records suppress their legacy connection too. Credential
    failure fails closed; never fall back to an older endpoint or API key.
    """
    settings = settings or get_settings()
    connections = {item.id: item for item in settings.moonraker.printers}
    rows = await session.scalars(select(Printer).order_by(Printer.printer_code))
    for printer in rows:
        if not printer.connection_managed:
            legacy = connections.get(printer.printer_code)
            if legacy is not None:
                connections[printer.printer_code] = legacy.model_copy(
                    update={
                        "name": printer.name,
                        "nozzle_diameter_mm": float(printer.nozzle_diameter_mm),
                        "power_device": printer.power_device,
                    }
                )
            continue
        connections.pop(printer.printer_code, None)
        if not printer.connection_enabled:
            continue
        base = printer.moonraker_base_url.rstrip("/")
        connections[printer.printer_code] = PrinterConfig(
            id=printer.printer_code,
            name=printer.name,
            base_url=base,
            websocket_url=base.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + "/websocket",
            api_key=SecretStr(decrypt_credential(settings, printer.encrypted_api_key))
            if printer.encrypted_api_key
            else None,
            nozzle_diameter_mm=float(printer.nozzle_diameter_mm),
            power_device=printer.power_device,
        )
    return list(connections.values())
