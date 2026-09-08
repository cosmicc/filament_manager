"""Render the shipped QQ-S pause lifecycle without executing physical motion."""

import ast
import configparser
from pathlib import Path
from typing import Any

import pytest
from test_build_plate_macros import ENVIRONMENT, printer_snapshot

PATH = Path("integrations/klipper/examples/flsun-qq-s-macros.cfg")
CONFIG = configparser.ConfigParser(interpolation=None, strict=True)
CONFIG.read(PATH)


def snapshot() -> dict[str, Any]:
    """Use independent copies of literal defaults and a homed delta status."""
    printer = printer_snapshot()
    for section in CONFIG.sections():
        if section.startswith("gcode_macro "):
            printer[section] = {
                key.removeprefix("variable_"): ast.literal_eval(value)
                for key, value in CONFIG.items(section)
                if key.startswith("variable_")
            }
    printer["toolhead"].update(
        homed_axes="xyz",
        extruder="extruder",
        cone_start_z=250,
        position={"x": 10, "y": 20, "z": 100},
        axis_maximum={"x": 125, "y": 125, "z": 300},
    )
    printer["gcode_move"] = {"gcode_position": {"x": 10, "y": 20, "z": 100}}
    printer["extruder"] = {"can_extrude": True}
    printer["virtual_sdcard"] = {"is_active": True}
    printer["print_stats"]["state"] = "printing"
    return printer


def render(name: str, printer: dict[str, Any], **params: str) -> str:
    """Render using Klipper delimiters, surfacing action errors as failures."""

    def fail(message: str) -> None:
        raise ValueError(message)

    return ENVIRONMENT.from_string(CONFIG.get("gcode_macro " + name, "gcode")).render(
        printer=printer,
        params=params,
        rawparams="",
        action_raise_error=fail,
        action_respond_info=lambda message: "INFO " + message,
    )


def test_every_template_compiles_and_literals_are_valid() -> None:
    for section in CONFIG.sections():
        if CONFIG.has_option(section, "gcode"):
            ENVIRONMENT.from_string(CONFIG.get(section, "gcode"))
    assert not CONFIG.has_section("gcode_macro BED_MESH_CALIBRATE")
    assert CONFIG.get("gcode_macro M25", "rename_existing") == "M25.1"
    assert CONFIG.get("gcode_macro M24", "rename_existing") == "M24.1"


def test_capture_precedes_retract_and_lift_precedes_xy() -> None:
    result = render("PAUSE", snapshot())
    assert result.index("BASE_PAUSE") < result.index("SAVE_GCODE_STATE NAME=FM_PRINT_PAUSE")
    assert result.index("M83") < result.index("G1 E-1.5") < result.index("G1 Z10") < result.index("G1 X125")
    assert "G28" not in result
    assert "PARK_NOZZLE" not in result
    assert "RESTORE_GCODE_STATE NAME=FM_PRINT_PAUSE MOVE=0" in result


def test_duplicate_pause_never_overwrites_saved_position() -> None:
    printer = snapshot()
    printer["pause_resume"]["is_paused"] = True
    result = render("PAUSE", printer)
    assert "original print position retained" in result
    assert "BASE_PAUSE" not in result
    assert "SAVE_GCODE_STATE" not in result
    assert "G1" not in result


@pytest.mark.parametrize("cause", ["high_z", "unhomed", "preflight", "invalid_xy"])
def test_unsafe_pause_still_stops_without_xyz_motion(cause: str) -> None:
    printer = snapshot()
    if cause == "high_z":
        printer["toolhead"]["position"]["z"] = 280
    elif cause == "unhomed":
        printer["toolhead"]["homed_axes"] = ""
    elif cause == "preflight":
        printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"]["start_pending"] = 1
    result = render("PAUSE", printer, **({"X": "999"} if cause == "invalid_xy" else {}))
    assert "BASE_PAUSE" in result
    assert "G1 X" not in result and "G1 Z" not in result and "G28" not in result


def test_runout_after_sd_stop_still_captures_and_parks() -> None:
    printer = snapshot()
    printer["virtual_sdcard"]["is_active"] = False
    printer["print_stats"]["state"] = "paused"
    assert "G1 X125" in render("PAUSE", printer)
    assert "PAUSE" in CONFIG.get("gcode_macro FILAMENT_RUNOUT", "gcode")


def test_cold_pause_does_not_retract_or_invent_a_prime() -> None:
    printer = snapshot()
    printer["extruder"]["can_extrude"] = False
    result = render("PAUSE", printer)
    assert "G1 E" not in result
    assert "VARIABLE=retracted VALUE=0" in result


def test_resume_moves_above_saved_xy_before_native_descent() -> None:
    printer = snapshot()
    printer["pause_resume"]["is_paused"] = True
    printer["gcode_macro PAUSE"].update(valid=1, x=10, y=20, safe_z=110, parked=1, retracted=1.5)
    result = render("RESUME", printer)
    assert result.index("RESTORE_GCODE_STATE") < result.index("_QQS_RESUME_RETURN")
    result = render("_QQS_RESUME_RETURN", printer, VELOCITY="50")
    assert (
        result.index("G1 E1.5")
        < result.index("G1 Z110")
        < result.index("G1 X10 Y20")
        < result.index("BASE_RESUME")
    )
    assert "VARIABLE=retracted VALUE=0" in result


@pytest.mark.parametrize("cause", ["unhomed", "cold", "different_tool", "workflow", "invalid", "speed"])
def test_unsafe_resume_is_refused_before_motion(cause: str) -> None:
    printer = snapshot()
    printer["pause_resume"]["is_paused"] = True
    printer["gcode_macro PAUSE"]["valid"] = 1
    if cause == "unhomed":
        printer["toolhead"]["homed_axes"] = ""
    elif cause == "cold":
        printer["extruder"]["can_extrude"] = False
    elif cause == "different_tool":
        printer["toolhead"]["extruder"] = "extruder1"
    elif cause == "workflow":
        printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"]["phase"] = "inserting"
    elif cause == "invalid":
        printer["gcode_macro PAUSE"]["valid"] = 0
    with pytest.raises(ValueError):
        render("RESUME", printer, **({"VELOCITY": "0"} if cause == "speed" else {}))


def test_sd_and_slicer_routes_preserve_preflight_exception() -> None:
    printer = snapshot()
    assert render("M25", printer).strip() == "PAUSE"
    assert render("M0", printer).strip() == "PAUSE"
    assert render("M1", printer).strip() == "PAUSE"
    printer["gcode_macro FILAMENT_MANAGER_SPOOL_STATE"]["start_pending"] = 1
    assert render("M25", printer).strip() == "M25.1"
    printer["pause_resume"]["is_paused"] = True
    assert render("M24", printer).strip() == "RESUME"
    with pytest.raises(ValueError, match="Cancel"):
        render("G28", printer)
