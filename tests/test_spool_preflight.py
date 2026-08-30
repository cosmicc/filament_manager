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
    cura_product_material_guid,
    cura_product_scope_id,
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


def test_product_material_guid_is_stable_across_profile_snapshots() -> None:
    """Semantic product scope, rather than immutable revision ID, owns Cura identity."""

    product_id = UUID("a8111abe-1bf9-45d6-9303-cd4b328b08c4")
    printer_id = UUID("c27538ec-763a-4f5e-9e28-c2921652329d")

    assert cura_product_scope_id(product_id, printer_id, "0.40000") == cura_product_scope_id(
        product_id,
        printer_id,
        "0.4",
    )
    assert cura_product_material_guid(product_id, printer_id, "0.4") == cura_material_guid(
        "product",
        cura_product_scope_id(product_id, printer_id, "0.4"),
    )


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
    manual_spools = [[17, "FM-001-PLA-Blue"]]
    print_temperatures = {"17": "210.0"}
    temperatures = {"17": "215.0"}
    catalog = SpoolPreflightCatalog(
        materials=materials,
        manual_spools=manual_spools,
        print_temperatures=print_temperatures,
        temperatures=temperatures,
        revision=build_catalog_revision(materials, manual_spools, print_temperatures, temperatures),
    )

    for variable, literal in (
        ("catalog", catalog.materials_literal()),
        ("manual_spools", catalog.manual_spools_literal()),
        ("print_temperatures", catalog.print_temperatures_literal()),
        ("temperatures", catalog.temperatures_literal()),
    ):
        command = (
            f"SET_GCODE_VARIABLE MACRO=FILAMENT_MANAGER_SPOOL_STATE VARIABLE={variable} VALUE='{literal}'"
        )
        parameters = dict(token.split("=", 1) for token in shlex.split(command)[1:])
        assert ast.literal_eval(parameters["VALUE"]) in (
            materials,
            manual_spools,
            print_temperatures,
            temperatures,
        )


def test_macro_reference_compiles_and_preserves_existing_motion_macros() -> None:
    """The reference owns public spool commands and calls reserved motion routines."""

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
    assert parser.get(spool_state_section, "variable_macro_version") == '"0.6.5"'
    spool_state_gcode = parser.get(spool_state_section, "gcode")
    assert "state.macro_version" in spool_state_gcode
    assert '"; macro=" ~ macro_version' in spool_state_gcode
    assert parser.get(spool_state_section, "variable_catalog_revision") == '"' + ("0" * 64) + '"'
    assert ast.literal_eval(parser.get(spool_state_section, "variable_manual_spools")) == []
    assert ast.literal_eval(parser.get(spool_state_section, "variable_print_temperatures")) == {}
    assert parser.get(spool_state_section, "variable_material_guid") == '"UNSET"'
    restore_state = parser.get("delayed_gcode _FILAMENT_MANAGER_RESTORE_STATE", "gcode")
    assert 'default("' + ("0" * 64) + '", true)' in restore_state

    assert not parser.has_section("gcode_macro START_PRINT")
    assert not parser.has_section("gcode_macro END_PRINT")
    assert not parser.has_option("gcode_macro M600", "rename_existing")
    assert "M600.1" not in MACRO_PATH.read_text(encoding="utf-8")
    assert not parser.has_option("gcode_macro LOAD_FILAMENT", "rename_existing")
    assert not parser.has_option("gcode_macro UNLOAD_FILAMENT", "rename_existing")
    assert not parser.has_section("gcode_macro _FILAMENT_MANAGER_HARDWARE_LOAD")
    assert not parser.has_section("gcode_macro _FILAMENT_MANAGER_HARDWARE_UNLOAD")

    load_target = parser.get("gcode_macro FILAMENT_MANAGER_LOAD_TARGET", "gcode")
    assert "_FILAMENT_MANAGER_PROMPT_ALL_SPOOLS" in load_target
    assert "Select a Target Spool for FILAMENT_MANAGER_LOAD_TARGET" not in load_target
    assert not parser.has_section("gcode_macro _FILAMENT_MANAGER_USE_STAGED_TARGET")
    assert "FILAMENT_MANAGER_LOAD_TARGET" in parser.get("gcode_macro LOAD_FILAMENT", "gcode")
    assert "_FILAMENT_MANAGER_HARDWARE_LOAD" in parser.get(
        "gcode_macro _FILAMENT_MANAGER_LOAD_SELECTED", "gcode"
    )
    assert "_FILAMENT_MANAGER_HARDWARE_UNLOAD" in parser.get("gcode_macro UNLOAD_FILAMENT", "gcode")
    manual_prompt = parser.get("gcode_macro _FILAMENT_MANAGER_PROMPT_ALL_SPOOLS", "gcode")
    assert "state.manual_spools" in manual_prompt
    assert "published profile" not in manual_prompt
    print_selector = parser.get("gcode_macro _FILAMENT_MANAGER_SELECT_PRINT_SPOOL", "gcode")
    assert "state.print_temperatures" in print_selector
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


def test_macro_virtual_sd_resume_contract_handles_every_preflight_exit() -> None:
    """Only the app-owned M25 latch may resume a safely paused Cura file."""

    parser = configparser.RawConfigParser(strict=True)
    assert parser.read(MACRO_PATH)

    start_gate = parser.get("gcode_macro FILAMENT_MANAGER_START_PRINT", "gcode")
    assert start_gate.index("M25") < start_gate.index("VARIABLE=resume_virtual_sd VALUE=1")

    spool_check = parser.get("gcode_macro _FILAMENT_MANAGER_CHECK_PRINT_SPOOL", "gcode")
    assert spool_check.index("M25") < spool_check.index("VARIABLE=resume_virtual_sd VALUE=1")

    continue_start = parser.get("gcode_macro _FILAMENT_MANAGER_CONTINUE_START", "gcode")
    assert continue_start.index("START_PRINT BED_TEMP=") < continue_start.index(
        "UPDATE_DELAYED_GCODE ID=_FILAMENT_MANAGER_RESUME_PRINT_START DURATION=0.25"
    )
    assert "VARIABLE=resume_virtual_sd VALUE=0" not in continue_start

    delayed_resume = parser.get("delayed_gcode _FILAMENT_MANAGER_RESUME_PRINT_START", "gcode")
    assert "state.resume_virtual_sd|int" in delayed_resume
    assert 'print_state == "paused"' in delayed_resume
    assert "not printer.pause_resume.is_paused" in delayed_resume
    assert "printer.virtual_sdcard.is_active and waiting_for_mesh == 0" not in delayed_resume
    assert delayed_resume.index("M24") < delayed_resume.index("VARIABLE=resume_virtual_sd VALUE=0")
    assert "UPDATE_DELAYED_GCODE ID=_FILAMENT_MANAGER_RESUME_PRINT_START DURATION=0.25" in (delayed_resume)

    cancel_print = parser.get("gcode_macro CANCEL_PRINT", "gcode")
    abort = parser.get("gcode_macro FILAMENT_MANAGER_ABORT", "gcode")
    for cancellation_path in (cancel_print, abort):
        assert "UPDATE_DELAYED_GCODE ID=_FILAMENT_MANAGER_RESUME_PRINT_START DURATION=0" in (
            cancellation_path
        )
        assert "VARIABLE=resume_virtual_sd VALUE=0" in cancellation_path
    assert 'print_state in ["printing", "paused"]' in abort
    assert "file_loaded" in abort
    assert "CANCEL_PRINT" in abort
    assert "file_loaded and not printer.virtual_sdcard.is_active" in cancel_print
    assert "not printer.pause_resume.is_paused" in cancel_print
    assert cancel_print.index("SDCARD_RESET_FILE") < cancel_print.index(
        "_FILAMENT_MANAGER_ORIGINAL_CANCEL_PRINT"
    )

    plate_selector = parser.get("gcode_macro SELECT_BUILD_PLATE", "gcode")
    assert '"gcode_macro _START_PRINT_CONTINUE" not in printer' in plate_selector
    assert plate_selector.index("MACRO=START_PRINT VARIABLE=waiting_for_mesh VALUE=0") < (
        plate_selector.index("_START_PRINT_CONTINUE BED_TEMP=")
    )
    assert plate_selector.index("_START_PRINT_CONTINUE BED_TEMP=") < plate_selector.index(
        "UPDATE_DELAYED_GCODE ID=_FILAMENT_MANAGER_RESUME_PRINT_START DURATION=0.25"
    )
