"""Bounded G-code extraction and exact-profile comparison tests."""

import json

from filament_manager.domain.gcode_inspection import extract_gcode_metadata, inspect_gcode


def cura_tail(settings: str) -> str:
    """Encode the same JSON/INI envelope Cura writes after the toolpath."""

    payload = json.dumps({"global_quality": f"[general]\nname = Dimensional\n[values]\n{settings}"})
    return f";SETTING_3 {payload}"


def test_cura_metadata_is_extracted_without_evaluating_content() -> None:
    """Supported metadata is normalized while malicious-looking values remain inert text."""

    result = extract_gcode_metadata(
        {"estimated_time": 125, "filament_total": "1234.5", "nozzle_diameter": "0.4"},
        ";Generated with Cura_SteamEngine 5.10.1\n"
        ";MATERIAL_GUID=12345678-1234-1234-1234-123456789abc\n"
        "FILAMENT_MANAGER_START_PRINT BED_TEMP=75 REGULAR_BED_TEMP=70\n"
        "SET_PRESSURE_ADVANCE ADVANCE=0.035\n",
        cura_tail(
            "material_print_temperature = 225\nmaterial_bed_temperature = 70\n"
            "material_bed_temperature_layer_0 = 75\n"
            "material_flow = 98.000\nlayer_height = 0.20\nline_width = 0.44\n"
            "retraction_retract_speed = 35\nretraction_prime_speed = 31\n"
            "support_enable = true\nquality_definition = Test Printer\n"
            "unsafe = __import__('os').system('false')\n"
        ),
    )

    assert result["slicer"] == "Cura"
    assert result["slicer_version"] == "5.10.1"
    assert result["material_guid"] == "12345678-1234-1234-1234-123456789abc"
    assert result["extruder_temp_c"] == "225"
    assert result["bed_temp_c"] == "70"
    assert result["initial_bed_temp_c"] == "75"
    assert result["flow_percent"] == "98.000"
    assert result["pressure_advance"] == "0.035"
    assert result["retraction_speed_mm_s"] == "35"
    assert result["retraction_prime_speed_mm_s"] == "31"
    assert result["support_configuration"] == {
        "enabled": True,
        "structure": None,
        "placement": None,
    }


def test_all_bounded_cura_settings_are_retained_by_scope_as_inert_text() -> None:
    """History keeps global and extruder values, including unevaluated formulas."""

    payload = json.dumps(
        {
            "global_quality": (
                "[general]\nname = Fine\ndefinition = printer_a\n[values]\n"
                "layer_height = 0.16\nwall_line_count = =max(2, machine_nozzle_size)\n"
            ),
            "extruder_quality": [
                "[general]\nname = Extruder 1\n[metadata]\nposition = 0\n[values]\n"
                "material_print_temperature = 225\nretraction_amount = 0.8\n"
            ],
        }
    )
    result = inspect_gcode(
        {"slicer": "Cura", "layer_height": "0.16", "filament_total": "1000"},
        "",
        f";SETTING_3 {payload}",
        expected_profile={"extruder_temp_c": "225"},
        expected_material_guid=None,
        expected_machine_name=None,
    )

    assert result.cura_settings["available"] is True
    assert result.cura_settings["setting_count"] == 4
    global_scope = result.cura_settings["global"]
    assert isinstance(global_scope, dict)
    assert global_scope["settings"] == {
        "layer_height": "0.16",
        "wall_line_count": "=max(2, machine_nozzle_size)",
    }
    extruders = result.cura_settings["extruders"]
    assert isinstance(extruders, list)
    assert extruders[0]["position"] == "0"
    assert extruders[0]["settings"] == {
        "material_print_temperature": "225",
        "retraction_amount": "0.8",
    }


def test_cura_setting_capture_omits_connection_and_credential_values() -> None:
    """Potential secrets and external locations never enter immutable history."""

    payload = json.dumps(
        {
            "global_quality": (
                "[values]\nlayer_height = 0.2\napi_key = private\nservice_url = https://printer.invalid\n"
            )
        }
    )
    result = inspect_gcode(
        {"slicer": "Cura", "layer_height": "0.2", "filament_total": "1000"},
        "",
        f";SETTING_3 {payload}",
        expected_profile={},
        expected_material_guid=None,
        expected_machine_name=None,
    )

    global_scope = result.cura_settings["global"]
    assert isinstance(global_scope, dict)
    assert global_scope["settings"] == {"layer_height": "0.2"}
    assert result.cura_settings["filtered_count"] == 2


def test_profile_mismatches_are_structured_and_decimal_tolerant() -> None:
    """Only semantically different values become actionable mismatch records."""

    result = inspect_gcode(
        {"slicer": "Cura", "layer_height": "0.2", "filament_total": "1200"},
        ";MATERIAL_GUID=12345678-1234-1234-1234-123456789abc\n",
        cura_tail(
            "material_print_temperature = 240\nmaterial_bed_temperature = 70.0\n"
            "material_bed_temperature_layer_0 = 75\n"
            "material_flow = 98.000\nmachine_nozzle_size = 0.400\n"
            "retraction_retract_speed = 35\nretraction_prime_speed = 30\n"
        ),
        expected_profile={
            "extruder_temp_c": "225",
            "bed_temp_c": "70",
            "initial_bed_temp_c": "65",
            "flow_percent": "98",
            "nozzle_diameter_mm": "0.4",
            "retraction_speed_mm_s": "35",
            "retraction_prime_speed_mm_s": "32",
        },
        expected_material_guid="12345678-1234-1234-1234-123456789abc",
        expected_machine_name=None,
    )

    assert result.mismatches == (
        {
            "field": "extruder_temp_c",
            "label": "printing temperature",
            "gcode_value": "240",
            "profile_value": "225",
        },
        {
            "field": "initial_bed_temp_c",
            "label": "initial layer build plate temperature",
            "gcode_value": "75",
            "profile_value": "65",
        },
        {
            "field": "retraction_prime_speed_mm_s",
            "label": "retraction prime speed",
            "gcode_value": "30",
            "profile_value": "32",
        },
    )
    assert result.warnings == ()


def test_first_layer_bed_temperature_is_not_compared_as_regular_temperature() -> None:
    """Initial-only evidence must not create a false regular-bed mismatch."""

    metadata = {"slicer": "Cura", "first_layer_bed_temp": "60"}
    header = "FILAMENT_MANAGER_START_PRINT BED_TEMP=60\nM190 S60\n"
    tail = cura_tail("material_print_temperature = 220\n")

    matching = inspect_gcode(
        metadata,
        header,
        tail,
        expected_profile={
            "bed_temp_c": "55",
            "initial_bed_temp_c": "60",
        },
        expected_material_guid=None,
        expected_machine_name=None,
    )

    assert "bed_temp_c" not in matching.extracted
    assert matching.extracted["initial_bed_temp_c"] == "60"
    assert matching.mismatches == ()

    initial_mismatch = inspect_gcode(
        metadata,
        header,
        tail,
        expected_profile={
            "bed_temp_c": "55",
            "initial_bed_temp_c": "55",
        },
        expected_material_guid=None,
        expected_machine_name=None,
    )

    assert initial_mismatch.mismatches == (
        {
            "field": "initial_bed_temp_c",
            "label": "initial layer build plate temperature",
            "gcode_value": "60",
            "profile_value": "55",
        },
    )


def test_stale_quality_payload_cannot_override_resolved_bed_temperature_evidence() -> None:
    """Only explicit managed start tokens may represent the resolved regular bed value."""

    stale_quality_tail = cura_tail("material_bed_temperature = 60\nmaterial_bed_temperature_layer_0 = 60\n")
    without_regular_evidence = inspect_gcode(
        {"slicer": "Cura", "first_layer_bed_temp": "60"},
        "FILAMENT_MANAGER_START_PRINT BED_TEMP=60\nM190 S60\n",
        stale_quality_tail,
        expected_profile={"bed_temp_c": "55", "initial_bed_temp_c": "60"},
        expected_material_guid=None,
        expected_machine_name=None,
    )

    assert "bed_temp_c" not in without_regular_evidence.extracted
    assert without_regular_evidence.mismatches == ()

    explicit_regular_mismatch = inspect_gcode(
        {"slicer": "Cura", "first_layer_bed_temp": "60"},
        "FILAMENT_MANAGER_START_PRINT BED_TEMP=60 REGULAR_BED_TEMP=58\nM190 S60\n",
        stale_quality_tail,
        expected_profile={"bed_temp_c": "55", "initial_bed_temp_c": "60"},
        expected_material_guid=None,
        expected_machine_name=None,
    )

    assert explicit_regular_mismatch.mismatches == (
        {
            "field": "bed_temp_c",
            "label": "build plate temperature",
            "gcode_value": "58",
            "profile_value": "55",
        },
    )


def test_unresolved_profile_is_explicitly_unavailable_for_block_policy() -> None:
    """The service can distinguish a missing exact profile from a successful inspection."""

    result = inspect_gcode(
        {"slicer": "Cura", "layer_height": "0.2", "filament_total": "1200"},
        "",
        "",
        expected_profile=None,
        expected_material_guid=None,
        expected_machine_name=None,
    )

    assert result.mismatches == ()
    assert result.warnings == ("No exact managed material profile could be resolved for this G-code file.",)
