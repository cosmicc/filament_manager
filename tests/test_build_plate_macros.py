"""Render plate macros with Klipper's delimiters and explicit printer snapshots.

These tests verify emitted commands and failure gates, not physical probe motion.
Delayed G-code renders only a helper name; the helper reads fresh state after
Klipper's G-code mutex releases the native calibration command.
"""

import ast
import configparser
import shlex
from typing import Any

import pytest
from jinja2 import Environment

MACROS = configparser.RawConfigParser()
MACROS.read("integrations/klipper/filament-manager-macros.cfg")
ENVIRONMENT = Environment(
    block_start_string="{%",
    block_end_string="%}",
    variable_start_string="{",
    variable_end_string="}",
    autoescape=False,  # noqa: S701 - G-code, not HTML
)


def printer_snapshot() -> dict[str, Any]:
    """Return an idle, initialized printer with a persisted Side B selection."""

    printer: dict[str, Any] = {
        "bed_mesh": {"profiles": {"P4": {}, "P4b": {}}, "profile_name": "P4b"},
        "save_variables": {"variables": {"filament_manager_active_plate": "P4b"}},
        "print_stats": {"state": "standby"},
        "toolhead": {"estimated_print_time": 200.0},
        "manual_probe": {"is_active": False},
        "pause_resume": {"is_paused": False},
        "gcode_macro START_PRINT": {"waiting_for_mesh": 0},
    }
    for section in MACROS.sections():
        if section.startswith("gcode_macro "):
            printer[section] = {
                key.removeprefix("variable_"): ast.literal_eval(value)
                for key, value in MACROS.items(section)
                if key.startswith("variable_")
            }
    printer["gcode_macro FILAMENT_MANAGER_PLATE_STATE"]["selected_plate"] = "P4b"
    return printer


def render(name: str, printer: dict[str, Any], **params: str) -> str:
    """Render a macro; Klipper action errors abort before any command is emitted."""

    def fail(message: str) -> None:
        raise ValueError(message)

    return ENVIRONMENT.from_string(MACROS.get(f"gcode_macro {name}", "gcode")).render(
        printer=printer,
        params=params,
        rawparams=" ".join(f"{k}={v}" for k, v in params.items()),
        action_raise_error=fail,
        action_respond_info=lambda _message: "",
    )


def test_all_reference_templates_compile_with_klipper_delimiters() -> None:
    """Compile every macro, including conditional paths absent in ordinary tests."""

    for section in MACROS.sections():
        if MACROS.has_option(section, "gcode"):
            ENVIRONMENT.from_string(MACROS.get(section, "gcode"))


@pytest.mark.parametrize("state", ["printing", "paused", "unknown"])
@pytest.mark.parametrize(
    "macro", ["FILAMENT_MANAGER_CHANGE_SPOOL", "FILAMENT_MANAGER_LOAD_TARGET", "UNLOAD_FILAMENT"]
)
def test_ordinary_spool_macros_refuse_active_or_unknown_prints(state: str, macro: str) -> None:
    """Printer-side guards close the race after an app request was checked idle."""

    printer = printer_snapshot()
    printer["print_stats"]["state"] = state
    printer["pause_resume"] = {"is_paused": state == "paused"}
    spool = printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"]
    spool.update(initialized=1, phase="idle", loaded_spool_id=17, loaded_temp=210)
    with pytest.raises(ValueError, match="M600"):
        render(macro, printer, ID="18", TEMP="210")


@pytest.mark.parametrize("state", ["printing", "paused"])
def test_m600_remains_available_and_native_plate_load_is_blocked(state: str) -> None:
    """Deliberate filament replacement is the exception, never plate selection."""

    printer = printer_snapshot()
    printer["print_stats"]["state"] = state
    printer["pause_resume"] = {"is_paused": state == "paused"}
    printer["idle_timeout"] = {"state": "Printing"}
    printer["extruder"] = {"target": 210}
    printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"].update(
        initialized=1, phase="idle", loaded_spool_id=17, loaded_temp=210
    )
    assert "_FILAMENT_MANAGER_BEGIN_MANUAL_CHANGE" in render("M600", printer)
    with pytest.raises(ValueError, match="Cannot change build plate"):
        render("BED_MESH_PROFILE", printer, LOAD="P4b")


def test_startup_restores_exact_saved_side_without_a_prompt() -> None:
    """The user's parameterless startup call restores Side B while offline."""

    printer = printer_snapshot()
    printer["bed_mesh"]["profile_name"] = ""
    result = render("SELECT_BUILD_PLATE", printer)
    assert "BED_MESH_PROFILE LOAD=P4b" in result
    assert "SOURCE=restore" in result
    assert "action:prompt_begin" not in result
    assert "G28" not in result  # The user's startup owns homing and probe safety.
    chooser = render("SELECT_BUILD_PLATE", printer, CHOOSE="1")
    assert "action:prompt_begin Select Build Plate" in chooser
    assert "SELECT_BUILD_PLATE PLATE=P4b" in chooser


def test_missing_mesh_never_falls_back_to_another_plate() -> None:
    """Missing saved state warns at startup and blocks a pending print start."""

    printer = printer_snapshot()
    del printer["bed_mesh"]["profiles"]["P4b"]
    result = render("SELECT_BUILD_PLATE", printer)
    assert "BED_MESH_CLEAR" in result
    assert "BED_MESH_PROFILE LOAD=" not in result
    printer["gcode_macro START_PRINT"]["waiting_for_mesh"] = 1
    with pytest.raises(ValueError, match="Cannot start print"):
        render("SELECT_BUILD_PLATE", printer)


@pytest.mark.parametrize("state", ["printing", "paused"])
def test_plate_mutations_are_blocked_during_printing(state: str) -> None:
    """No startup, explicit selection, clear, or reconciliation changes a live mesh."""

    printer = printer_snapshot()
    printer["print_stats"]["state"] = state
    for name in (
        "SELECT_BUILD_PLATE",
        "FILAMENT_MANAGER_APPLY_BUILD_PLATE",
        "FILAMENT_MANAGER_CLEAR_BUILD_PLATE",
    ):
        with pytest.raises(ValueError):
            render(name, printer)


def test_calibration_receipt_requires_native_success_and_preserves_unknown_time() -> None:
    """Failed/aborted calibration and plain profile loads cannot create evidence."""

    printer = printer_snapshot()
    state = printer["gcode_macro FILAMENT_MANAGER_PLATE_STATE"]
    state.update(calibrating=1, capture_target="P4b", capture_profile="default")
    printer["bed_mesh"]["profile_name"] = ""
    assert "SAVE_VARIABLE VARIABLE=filament_manager_mesh_calibrations" not in render(
        "_FILAMENT_MANAGER_CAPTURE_MESH_RESULT",
        printer,
    )
    printer["bed_mesh"]["profile_name"] = "default"
    result = render("_FILAMENT_MANAGER_CAPTURE_MESH_RESULT", printer)
    assert "BED_MESH_PROFILE SAVE=P4b" in result
    receipt_line = next(line for line in result.splitlines() if "SAVE_VARIABLE VARIABLE=" in line)
    receipt = ast.literal_eval(shlex.split(receipt_line)[-1].split("=", 1)[1])
    assert receipt == {"P4b": {"sequence": 1, "time": 0}}
    state.update(clock_ready=1, clock_offset=1_783_000_000.0)
    result = render("_FILAMENT_MANAGER_CAPTURE_MESH_RESULT", printer)
    assert "1783000200.0" in result
    load = render("BED_MESH_PROFILE", printer, LOAD="P4b")
    assert "VARIABLE=calibrating VALUE=0" in load
    assert "filament_manager_mesh_calibrations" not in load


def test_manual_probe_waits_for_completion_even_after_thirty_minutes() -> None:
    """An ongoing manual probe must never allow background mesh restoration."""

    printer = printer_snapshot()
    printer["manual_probe"]["is_active"] = True
    printer["gcode_macro FILAMENT_MANAGER_PLATE_STATE"].update(calibrating=1, capture_attempts=1900)
    result = render("_FILAMENT_MANAGER_CAPTURE_MESH_RESULT", printer)
    assert "DURATION=1" in result
    assert "VARIABLE=calibrating VALUE=0" not in result
    assert "filament_manager_mesh_calibrations" not in result


def test_adaptive_mesh_is_not_saved_as_a_full_plate_calibration() -> None:
    """Adaptive/custom calibration retains native arguments without side receipts."""

    result = render("BED_MESH_CALIBRATE", printer_snapshot(), ADAPTIVE="1")
    assert "_FILAMENT_MANAGER_NATIVE_BED_MESH_CALIBRATE ADAPTIVE=1" in result
    assert "VARIABLE=capture_target VALUE=\"'P4b'\"" not in result
    assert result.index("BED_MESH_CLEAR") < result.index("UPDATE_DELAYED_GCODE")


def test_native_load_receipt_is_after_success_and_only_for_idle_exact_sides() -> None:
    """Native loads update selection, not calibration; app/startup loads bypass this receipt."""

    printer = printer_snapshot()
    result = render("BED_MESH_PROFILE", printer, LOAD="P4b")
    assert result.index("_FILAMENT_MANAGER_NATIVE_BED_MESH_PROFILE") < result.index(
        "_FILAMENT_MANAGER_LOADED_PLATE"
    )
    receipt = render("_FILAMENT_MANAGER_LOADED_PLATE", printer)
    assert "PLATE=P4b SOURCE=manual" in receipt
    assert "mesh_calibrations" not in receipt
    for state in ("printing", "paused", "unknown"):
        printer["print_stats"]["state"] = state
        assert "SAVE_VARIABLE" not in render("_FILAMENT_MANAGER_LOADED_PLATE", printer)
    printer["print_stats"]["state"] = "standby"
    printer["bed_mesh"]["profile_name"] = "custom"
    assert "SAVE_VARIABLE" not in render("_FILAMENT_MANAGER_LOADED_PLATE", printer)
    assert "_FILAMENT_MANAGER_NATIVE_BED_MESH_PROFILE LOAD=P4b" in render("SELECT_BUILD_PLATE", printer)
