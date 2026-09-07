"""Live printer safety and queued ordinary spool request regressions."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from filament_manager.api.errors import ApiError
from filament_manager.api.printer_safety import require_idle_printer
from filament_manager.clients.moonraker import MoonrakerBedMeshState, MoonrakerClient, MoonrakerError
from filament_manager.config import MoonrakerConfig, PrinterConfig, Settings


def safety_settings() -> Settings:
    """Supply only the configured connector required by the isolated safety check."""

    printer = PrinterConfig(
        id="test",
        name="Test",
        base_url="http://printer.invalid",
        websocket_url="ws://printer.invalid/websocket",
        nozzle_diameter_mm=Decimal("0.4"),
    )
    return Settings.model_construct(moonraker=MoonrakerConfig(printers=[printer]))


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["printing", "paused", "unknown", "standby"])
@pytest.mark.parametrize("calibrating", [False, True])
async def test_live_configuration_guard(
    state: str, calibrating: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only confirmed idle state without probing authorizes ordinary changes."""

    live = MoonrakerBedMeshState((), None, print_state=state, calibrating=calibrating)
    monkeypatch.setattr(MoonrakerClient, "bed_mesh_state", AsyncMock(return_value=live))
    if state == "standby" and not calibrating:
        assert await require_idle_printer("test", safety_settings()) == live
    else:
        with pytest.raises(ApiError) as error:
            await require_idle_printer("test", safety_settings())
        assert error.value.status_code == 409
        assert error.value.code == "printer_busy"


@pytest.mark.asyncio
async def test_unavailable_printer_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not expose upstream errors or permit changes when live checks fail."""

    monkeypatch.setattr(MoonrakerClient, "bed_mesh_state", AsyncMock(side_effect=MoonrakerError("private")))
    with pytest.raises(ApiError) as error:
        await require_idle_printer("test", safety_settings())
    assert error.value.status_code == 502
    assert "private" not in str(error.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["printing", "paused"])
async def test_queued_spool_actions_send_no_gcode_when_print_starts(
    state: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recheck delivery rather than trust an earlier idle API request."""

    from types import SimpleNamespace

    client = MoonrakerClient(safety_settings().moonraker.printers[0])
    monkeypatch.setattr(client, "print_state", AsyncMock(return_value=SimpleNamespace(state=state)))
    post = AsyncMock()
    monkeypatch.setattr(client, "_post", post)
    with pytest.raises(MoonrakerError, match="idle"):
        await client.request_spool_change(spoolman_id=17, temperature_c=Decimal("210"), prompt_label="PLA")
    with pytest.raises(MoonrakerError, match="idle"):
        await client.request_spool_unload()
    post.assert_not_awaited()
