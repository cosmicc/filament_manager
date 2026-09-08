"""Optional macro receipts change presentation only, never printer/history state."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from test_build_plate_macros import printer_snapshot, render
from test_build_plates import printer_config

from filament_manager.clients.moonraker import MoonrakerClient


@pytest.mark.parametrize("state", ["printing", "paused", "standby", "complete"])
def test_print_acknowledgement_is_terminal_only(state: str) -> None:
    printer = printer_snapshot()
    printer["print_stats"] = {"state": state, "total_duration": 1200.5}
    output = render("FILAMENT_MANAGER_PRINT_ACKNOWLEDGE", printer)
    assert ("VARIABLE=acknowledged VALUE=1" in output) == (state == "complete")
    assert "SDCARD_RESET_FILE" not in output
    assert "SET_PRINT_STATS" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,acknowledged_duration,active,expected_ack,expected_remaining",
    [
        ("complete", 1200, 1, True, Decimal("1200")),
        ("complete", 1199, 1, False, Decimal("1200")),
        ("printing", 1200, 1, False, None),
        ("paused", 1200, 1, False, None),
        ("complete", 1200, 0, True, None),
    ],
)
async def test_optional_receipts_share_existing_telemetry_query(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    acknowledged_duration: int,
    active: int,
    expected_ack: bool,
    expected_remaining: Decimal | None,
) -> None:
    client = MoonrakerClient(printer_config())
    objects = {
        "print_stats": {"state": state, "filename": "part.gcode", "total_duration": 1200},
        "extruder": {"temperature": 25, "target": 0},
        "idle_timeout": {"state": "Idle", "idle_timeout": 600},
        "toolhead": {"estimated_print_time": 4000},
        "gcode_macro FILAMENT_MANAGER_PRINT_COMPLETE": {
            "acknowledged": 1,
            "acknowledged_duration": acknowledged_duration,
        },
        "gcode_macro _POWER_OFF_TIMER_STATE": {"active": active, "deadline": 5200},
    }
    get = AsyncMock(side_effect=[{"result": {"state": "ready"}}, {"result": {"objects": list(objects)}}])
    post = AsyncMock(return_value={"result": {"status": objects}})
    monkeypatch.setattr(client, "_get", get)
    monkeypatch.setattr(client, "_post", post)
    observed = await client.operational_state()
    assert observed.completion_acknowledged is expected_ack
    assert observed.power_off_remaining_seconds == expected_remaining
    assert observed.print_state == state
    assert observed.idle_timeout_seconds == Decimal("600")
    assert post.await_count == 1
    assert post.call_args.args[0] == "/printer/objects/query"
