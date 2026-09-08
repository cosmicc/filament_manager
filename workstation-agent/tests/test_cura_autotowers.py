"""Regress the pre-export adapter without requiring Cura or network access."""

import re
import sys
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from filament_manager_agent.cura_autotowers import AUTOTOWERS_COMPATIBILITY_CODE


@pytest.fixture
def adapter() -> Any:
    """Load precisely the source inserted into the generated managed plugin."""

    module = ModuleType("autotowers_adapter_test")
    module.re = re  # type: ignore[attr-defined]
    module.Logger = SimpleNamespace(log=lambda *args: None)  # type: ignore[attr-defined]
    exec(compile(AUTOTOWERS_COMPATIBILITY_CODE, "AutoTowersCompatibility", "exec"), module.__dict__)  # noqa: S102
    return module


def speed_processor(
    gcode: list[str],
    base_height: float,
    section_height: float,
    initial_layer_height: float,
    layer_height: float,
    start_retract_speed: float,
    retract_speed_change: float,
    enable_lcd_messages: bool,
    enable_advanced_gcode_comments: bool,
) -> list[str]:
    """Model the independently reproduced 4.1 contract, not third-party source.

    Before the first section the affected processor substitutes start minus step
    on E-only moves. Later sections deliberately vary speed. It mutates and
    returns the same list, and adds optional annotations to changed lines.
    """

    gcode[0] += ";AutoTowersGenerator: Retract Tower (speed) post-processing script version 4.1\n"
    height = Decimal(0)
    next_section = Decimal(str(base_height))
    speed = start_retract_speed - retract_speed_change
    for index, clump in enumerate(gcode):
        lines = clump.split("\n")
        for line_index, line in enumerate(lines):
            if line.startswith(";TIME_ELAPSED:"):
                break
            if re.match(r";LAYER:[0-9]+", line):
                height += Decimal(str(initial_layer_height if height == 0 else layer_height))
                if height > next_section:
                    speed += retract_speed_change
                    next_section += Decimal(str(section_height))
                continue
            if not line.startswith("G1 ") or any(axis in line for axis in "XYZ") or "E" not in line:
                continue
            match = re.search(r"F([-+]?[0-9]*\.?[0-9]+)", line.split(";")[0])
            if match is None:
                continue
            lines[line_index] = line.replace("F" + match[1], f"F{int(speed * 60)}")
            if enable_advanced_gcode_comments:
                lines[line_index] += (
                    f" ;AutoTowersGenerator: Changed retraction speed to {speed} mm/s ({speed * 60} mm/min)"
                )
        gcode[index] = "\n".join(lines)
    return gcode


def tower_gcode(absolute: bool = False) -> list[str]:
    """Use asymmetric feeds, inert metadata, and real layer/tail delimiters."""

    retract, prime = ("98", "100") if absolute else ("-2", "2")
    gcode = [";thumbnail begin\n;opaque-image-bytes\n;thumbnail end\n", "M82\n" if absolute else "M83\n"]
    for index in range(6):
        gcode.append(
            f";LAYER:{index}\nG1 F2400 E{retract}\nG1 F1800 E{prime}\n"
            f"G1 X10 Y20 F3000 E3\n;TIME_ELAPSED:{index}\n"
        )
    return [*gcode, ";SETTING_3 inert settings\n", "END_PRINT\n"]


def process(adapter: Any, gcode: list[str], **overrides: Any) -> list[str]:
    """Call with the same keyword parameters used by RetractTowerController."""

    parameters = {
        "base_height": 0.4,
        "section_height": 0.4,
        "initial_layer_height": 0.2,
        "layer_height": 0.2,
        "start_retract_speed": 10.0,
        "retract_speed_change": 10.0,
        "enable_lcd_messages": False,
        "enable_advanced_gcode_comments": True,
    }
    parameters.update(overrides)
    return adapter._wrap_autotowers_speed_processor(speed_processor)(gcode=gcode, **parameters)


@pytest.mark.parametrize("comments", [True, False])
@pytest.mark.parametrize("absolute", [True, False])
@pytest.mark.parametrize("start,step", [(10.0, 10.0), (5.0, 10.0), (35.0, 10.0), (50.0, -10.0)])
def test_preserves_base_and_leaves_test_sections_exact(
    adapter: Any, comments: bool, absolute: bool, start: float, step: float
) -> None:
    """Zero/negative/positive base bugs never justify changing tower sections."""

    original = tower_gcode(absolute)
    unchanged_processor = original.copy()
    parameters = {
        "base_height": 0.4,
        "section_height": 0.4,
        "initial_layer_height": 0.2,
        "layer_height": 0.2,
        "start_retract_speed": start,
        "retract_speed_change": step,
        "enable_lcd_messages": False,
        "enable_advanced_gcode_comments": comments,
    }
    speed_processor(unchanged_processor, **parameters)
    result = process(adapter, original.copy(), **parameters)
    assert result[1:4] == original[1:4]
    assert result[4:] == unchanged_processor[4:]
    assert result[0].startswith(original[0])
    assert result[0].count(adapter.AUTOTOWERS_CORRECTION_MARKER) == 1
    assert "G1 F0 " not in "".join(result)


def test_decimal_layer_boundary_and_positional_call(adapter: Any) -> None:
    """The base includes equality, including when binary floats would drift."""

    original = tower_gcode()
    wrapped = adapter._wrap_autotowers_speed_processor(speed_processor)
    result = wrapped(original.copy(), 0.6, 0.4, 0.2, 0.2, 10.0, 10.0, True, False)
    assert result[2:5] == original[2:5]
    assert "G1 F600 E-2" in result[5]


def test_preserves_positive_startup_retraction_and_original_comments(adapter: Any) -> None:
    """Restore original text, not inferred signs, guessed speeds, or all F0 moves."""

    original = tower_gcode()
    original[1] += "G1 F2100 E-1 ;base retraction\nG1 E1 F1700\n"
    original[2] += "G1 F1600 E-1 ;after elapsed: outside processor\n"
    result = process(adapter, original.copy())
    assert result[1:4] == original[1:4]


@pytest.mark.parametrize("line", ["G1 F0 E-2", "G1 F-60 E2", "G1 F2400 X1 E-2", ";G1 F0 E-2"])
def test_does_not_invent_missing_or_invalid_original_speeds(adapter: Any, line: str) -> None:
    """Only a real positive pre-processing E-only feed supplies a correction."""

    original = tower_gcode()
    original[2] = ";LAYER:0\n" + line + "\n"
    result = process(adapter, original.copy(), enable_advanced_gcode_comments=False)
    expected = original.copy()
    speed_processor(expected, 0.4, 0.4, 0.2, 0.2, 10.0, 10.0, False, False)
    assert result[2] == expected[2]


@pytest.mark.parametrize("failure", ["missing_section", "oversized", "invalid_height", "changed_extrusion"])
def test_unverifiable_correction_warns_without_partial_repair(
    adapter: Any, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Bound work and refuse ambiguous content without applying a partial guess."""

    warnings = []
    monkeypatch.setattr(adapter, "_autotowers_warning", lambda: warnings.append(True))
    original = tower_gcode()
    arguments = {
        "gcode": original.copy(),
        "base_height": 0.4,
        "section_height": 0.4,
        "initial_layer_height": 0.2,
        "layer_height": 0.2,
        "start_retract_speed": 10.0,
        "retract_speed_change": 10.0,
        "enable_lcd_messages": False,
        "enable_advanced_gcode_comments": False,
    }
    if failure == "missing_section":
        arguments["base_height"] = 200
    elif failure == "oversized":
        monkeypatch.setattr(adapter, "AUTOTOWERS_PREFIX_LIMIT", 10)
    elif failure == "invalid_height":
        arguments["base_height"] = -1
    if failure == "changed_extrusion":
        moves = adapter._autotowers_base_moves(arguments)
        result = speed_processor(**arguments)
        result[3] = result[3].replace("E-2", "E-3")
        before = result.copy()
        assert adapter._autotowers_restore_base(result, moves, arguments) is False
        assert result == before
    else:
        result = adapter._wrap_autotowers_speed_processor(speed_processor)(**arguments)
        assert warnings == [True]
        assert adapter.AUTOTOWERS_CORRECTION_MARKER not in result[0]


def test_installs_once_and_only_on_recognized_optional_processor(
    adapter: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not import absent plugins, touch distance processors, or double wrap."""

    module = ModuleType(adapter.AUTOTOWERS_SPEED_MODULE)
    module.__version__ = "4.1"  # type: ignore[attr-defined]
    module.execute = speed_processor  # type: ignore[attr-defined]
    other = ModuleType("AutoTowersGenerator.Postprocessing.RetractDistanceTower_PostProcessing")
    other.execute = speed_processor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, other.__name__, other)
    adapter._install_autotowers_compatibility()
    assert adapter.AUTOTOWERS_SPEED_MODULE not in sys.modules
    monkeypatch.setitem(sys.modules, module.__name__, module)
    adapter._install_autotowers_compatibility()
    installed = module.execute  # type: ignore[attr-defined]
    assert installed is not speed_processor
    adapter._install_autotowers_compatibility()
    assert module.execute is installed  # type: ignore[attr-defined]
    assert other.execute is speed_processor  # type: ignore[attr-defined]


@pytest.mark.parametrize("version,processor", [("5.0", speed_processor), ("4.1", lambda gcode: gcode)])
def test_unknown_contract_is_not_wrapped(
    adapter: Any, monkeypatch: pytest.MonkeyPatch, version: str, processor: Any
) -> None:
    """Future plugin changes require revalidation rather than optimistic mutation."""

    warnings = []
    monkeypatch.setattr(adapter, "_autotowers_warning", lambda: warnings.append(True))
    module = ModuleType(adapter.AUTOTOWERS_SPEED_MODULE)
    module.__version__ = version  # type: ignore[attr-defined]
    module.execute = processor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    adapter._install_autotowers_compatibility()
    assert module.execute is processor  # type: ignore[attr-defined]
    assert warnings == [True]
