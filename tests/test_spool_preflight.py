"""Physical-spool preflight identifiers, bounds, and macro contract tests."""

import ast
import configparser
import shlex
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from filament_manager.domain.spool_preflight import (
    SpoolPreflightCatalog,
    build_catalog_revision,
    cura_material_guid,
    spool_prompt_label,
)

MACRO_PATH = Path("integrations/klipper/filament-manager-macros.cfg")


def test_cura_material_guid_matches_the_workstation_material_identity() -> None:
    """The server catalog and workstation renderer derive the same stable GUID."""

    source_id = UUID("11111111-2222-3333-4444-555555555555")

    assert cura_material_guid("product", source_id) == str(
        uuid5(NAMESPACE_URL, f"filament-manager-product:{source_id}")
    )
    with pytest.raises(ValueError, match="unsupported"):
        cura_material_guid("unmanaged", source_id)


def test_prompt_label_removes_command_characters_and_bounds_length() -> None:
    """External inventory names cannot add Fluidd prompt commands or line breaks."""

    label = spool_prompt_label("FM 001", 'Vendor|RESPOND\n"', "PLA / Blue", "x" * 200)

    assert label.startswith("FM-001-Vendor-RESPOND-PLA-Blue-")
    assert len(label) == 96
    assert "|" not in label
    assert "\n" not in label


def test_catalog_literals_survive_klipper_extended_parameter_parsing() -> None:
    """Compact catalog JSON remains an AST literal after Klipper's shlex pass."""

    materials = {"11111111-2222-3333-4444-555555555555": [[17, "FM-001-PLA-Blue"]]}
    temperatures = {"17": "215.0"}
    catalog = SpoolPreflightCatalog(
        materials=materials,
        temperatures=temperatures,
        revision=build_catalog_revision(materials, temperatures),
    )

    for variable, literal in (
        ("catalog", catalog.materials_literal()),
        ("temperatures", catalog.temperatures_literal()),
    ):
        command = (
            f"SET_GCODE_VARIABLE MACRO=FILAMENT_MANAGER_SPOOL_STATE VARIABLE={variable} VALUE='{literal}'"
        )
        parameters = dict(token.split("=", 1) for token in shlex.split(command)[1:])
        assert ast.literal_eval(parameters["VALUE"]) in (materials, temperatures)


def test_macro_reference_compiles_and_preserves_existing_motion_macros() -> None:
    """The shipped reference wraps, rather than replaces, printer motion routines."""

    parser = configparser.RawConfigParser(strict=True)
    assert parser.read(MACRO_PATH)
    for section in parser.sections():
        if section.startswith(("gcode_macro ", "delayed_gcode ")):
            gcode = parser.get(section, "gcode")
            assert gcode.count("{%") == gcode.count("%}")
            assert gcode.count("{% if ") == gcode.count("{% endif %}")
            assert gcode.count("{% for ") == gcode.count("{% endfor %}")
        for option, value in parser.items(section):
            if option.startswith("variable_"):
                assert ast.literal_eval(value) != ""

    spool_state_section = "gcode_macro FILAMENT_MANAGER_SPOOL_STATE"
    assert parser.get(spool_state_section, "variable_catalog_revision") == '"' + ("0" * 64) + '"'
    assert parser.get(spool_state_section, "variable_material_guid") == '"UNSET"'
    restore_state = parser.get("delayed_gcode _FILAMENT_MANAGER_RESTORE_STATE", "gcode")
    assert 'default("' + ("0" * 64) + '", true)' in restore_state

    assert not parser.has_section("gcode_macro START_PRINT")
    assert not parser.has_section("gcode_macro END_PRINT")
    assert parser.get("gcode_macro M600", "rename_existing") == "M600.1"
    assert parser.get("gcode_macro LOAD_FILAMENT", "rename_existing") == "_FILAMENT_MANAGER_HARDWARE_LOAD"
    assert parser.get("gcode_macro UNLOAD_FILAMENT", "rename_existing") == "_FILAMENT_MANAGER_HARDWARE_UNLOAD"

    load_target = parser.get("gcode_macro FILAMENT_MANAGER_LOAD_TARGET", "gcode")
    assert "_FILAMENT_MANAGER_PROMPT_ALL_SPOOLS" in load_target
    assert "Select a Target Spool for FILAMENT_MANAGER_LOAD_TARGET" not in load_target
    assert not parser.has_section("gcode_macro _FILAMENT_MANAGER_USE_STAGED_TARGET")
    assert "FILAMENT_MANAGER_LOAD_TARGET" in parser.get("gcode_macro LOAD_FILAMENT", "gcode")
    spoolman_target = parser.get("gcode_macro FILAMENT_MANAGER_SPOOLMAN_TARGET", "gcode")
    assert "It will not become active in Filament Manager until" in spoolman_target

    plate_selector = parser.get("gcode_macro SELECT_BUILD_PLATE", "gcode")
    assert "printer.bed_mesh.profiles" in plate_selector
    assert "SELECT_BUILD_PLATE PLATE={profile}" in plate_selector

    begin_change = parser.get("gcode_macro _FILAMENT_MANAGER_BEGIN_CHANGE", "gcode")
    assert begin_change.index("_FILAMENT_MANAGER_HARDWARE_UNLOAD") < begin_change.index(
        "_FILAMENT_MANAGER_RECORD_LOADED ID=-1"
    )
    load_selected = parser.get("gcode_macro _FILAMENT_MANAGER_LOAD_SELECTED", "gcode")
    assert load_selected.index("_FILAMENT_MANAGER_HARDWARE_LOAD") < load_selected.index(
        "_FILAMENT_MANAGER_RECORD_LOADED ID="
    )
