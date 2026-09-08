"""Live, fail-closed guards for ordinary physical printer configuration changes."""

from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.clients.moonraker import MoonrakerBedMeshState, MoonrakerClient, MoonrakerError
from filament_manager.config import Settings, get_settings
from filament_manager.models.inventory import Printer
from filament_manager.services.printer_connections import configured_printers

from .errors import ApiError


async def selected_printer(
    session: AsyncSession, printer_id: UUID | None, settings: Settings | None = None
) -> Printer:
    """Never silently route an ambiguous physical action to the first printer."""
    connections = await configured_printers(session, settings or get_settings())
    if printer_id is None:
        if len(connections) != 1:
            raise ApiError(409, "printer_selection_required", "Select the printer for this action.")
        printer = await session.scalar(
            select(Printer).where(Printer.printer_code == connections[0].id).with_for_update()
        )
    else:
        printer = await session.get(Printer, printer_id, with_for_update=True)
    if printer is None or not any(item.id == printer.printer_code for item in connections):
        raise ApiError(409, "printer_not_configured", "Select an enabled, configured printer.")
    return printer


async def require_idle_printer(
    printer_code: str | None, settings: Settings, session: AsyncSession | None = None
) -> MoonrakerBedMeshState:
    """Confirm live idle/probe state, never infer safety from retained print history."""

    connections = (
        await configured_printers(session, settings) if session is not None else settings.moonraker.printers
    )
    configured = next((item for item in connections if item.id == printer_code), None)
    if configured is None:
        raise ApiError(status.HTTP_409_CONFLICT, "printer_not_configured", "Printer is not configured")
    try:
        live = await MoonrakerClient(configured).bed_mesh_state()
    except MoonrakerError as exc:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "printer_state_unavailable",
            "Cannot confirm that the printer is idle; try again when Moonraker is available",
        ) from exc
    if live.calibrating or live.print_state not in {"standby", "complete", "cancelled", "error"}:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "printer_busy",
            "Plate, nozzle, and spool changes require an idle printer. Use M600 for an in-print replacement.",
        )
    return live
