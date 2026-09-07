"""Live, fail-closed guards for ordinary physical printer configuration changes."""

from fastapi import status

from filament_manager.clients.moonraker import MoonrakerBedMeshState, MoonrakerClient, MoonrakerError
from filament_manager.config import Settings

from .errors import ApiError


async def require_idle_printer(printer_code: str | None, settings: Settings) -> MoonrakerBedMeshState:
    """Confirm live idle/probe state, never infer safety from retained print history."""

    configured = next((item for item in settings.moonraker.printers if item.id == printer_code), None)
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
