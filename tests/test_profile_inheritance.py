"""Sparse material-profile inheritance tests."""

from filament_manager.domain.profile_inheritance import (
    override_setting_keys,
    resolve_profile_settings,
    resolve_profile_settings_for_template_update,
    sparse_profile_overrides,
)


def _settings() -> dict[str, object]:
    return {
        "chamber_temp_c": None,
        "extruder_temp_c": "200.000",
        "bed_temp_c": "55",
        "flow_percent": "100",
        "print_speed_mm_s": "60",
        "outer_wall_speed_mm_s": None,
        "inner_wall_speed_mm_s": None,
        "infill_speed_mm_s": None,
        "top_bottom_speed_mm_s": None,
        "initial_layer_speed_mm_s": None,
        "travel_speed_mm_s": None,
        "support_speed_mm_s": None,
        "retraction_distance_mm": "5",
        "retraction_speed_mm_s": "40",
        "cooling_enabled": True,
        "cooling_min_percent": "50",
        "cooling_max_percent": "100",
        "support_overhang_angle_deg": "50",
        "tree_max_branch_angle_deg": "40",
        "pressure_advance": "0.10",
        "filament_density_g_cm3": "1.24",
        "preferred_build_plate_surface_id": None,
        "cura_extensions": {
            "retraction_enable": True,
            "cool_min_layer_time": "10",
        },
    }


def test_sparse_overrides_ignore_equivalent_decimals_and_resolve_removals() -> None:
    """Only semantic changes are owned by a filament profile."""

    base = _settings()
    desired = {
        **base,
        "extruder_temp_c": "205",
        "flow_percent": "100.0000",
        "cura_extensions": {
            "retraction_enable": True,
            "cool_min_layer_time": "10",
            "material_flow_layer_0": "98",
        },
    }

    overrides = sparse_profile_overrides(base, desired)

    assert overrides == {"extruder_temp_c": "205"}
    assert override_setting_keys(overrides) == {"extruder_temp_c"}
    resolved = resolve_profile_settings(base, overrides)
    assert resolved["extruder_temp_c"] == "205"
    assert resolved["flow_percent"] == "100"
    assert resolved["cura_extensions"] == {
        "retraction_enable": True,
        "cool_min_layer_time": "10",
    }


def test_sparse_overrides_treat_numeric_json_and_decimal_text_as_equal() -> None:
    """Database numeric strings do not create phantom custom settings."""

    base = {
        **_settings(),
        "initial_bed_temp_c": 60,
        "bed_temp_c": 60.0,
        "cura_extensions": {"material_flow_layer_0": 100},
    }
    desired = {
        **base,
        "initial_bed_temp_c": "60.00000",
        "bed_temp_c": "60.0",
        "cura_extensions": {"material_flow_layer_0": "100.000"},
    }

    assert sparse_profile_overrides(base, desired) == {}


def test_template_update_drops_override_that_now_matches_template() -> None:
    """A value equal to the new template becomes inherited after save."""

    current = {**_settings(), "initial_bed_temp_c": "70"}
    newer = {**_settings(), "initial_bed_temp_c": 70}

    resolved, overrides = resolve_profile_settings_for_template_update(
        newer,
        current,
        {"initial_bed_temp_c": "70.000"},
    )

    assert resolved["initial_bed_temp_c"] == "70.000"
    assert overrides == {}


def test_template_update_preserves_profile_overrides_but_owns_template_only_settings() -> None:
    """Moving a base retains profile controls and replaces template-only values."""

    original_extensions = _settings()["cura_extensions"]
    assert isinstance(original_extensions, dict)
    base = {
        **_settings(),
        "cura_extensions": {
            **original_extensions,
            "acceleration_print": "5000",
            "klipper_smooth_time_factor": "0.04",
        },
    }
    overrides = {
        "extruder_temp_c": "205",
        "pressure_advance": "0.13",
        "cura_extensions": {
            "acceleration_print": "9000",
            "klipper_smooth_time_factor": "0.08",
        },
    }
    newer = {**base, "cooling_max_percent": "80", "extruder_temp_c": "210"}

    resolved = resolve_profile_settings(newer, overrides)

    assert resolved["extruder_temp_c"] == "205"
    assert resolved["pressure_advance"] == "0.13"
    assert resolved["cooling_max_percent"] == "80"
    assert resolved["cura_extensions"]["acceleration_print"] == "5000"  # type: ignore[index]
    assert resolved["cura_extensions"]["klipper_smooth_time_factor"] == "0.04"  # type: ignore[index]
    assert sparse_profile_overrides(newer, resolve_profile_settings(newer, overrides)) == {
        "extruder_temp_c": "205",
        "pressure_advance": "0.13",
    }
    assert override_setting_keys(overrides) == {"extruder_temp_c", "pressure_advance"}


def test_template_update_preserves_custom_regular_fan() -> None:
    """A calibrated filament may retain a custom regular fan speed."""

    current = _settings()
    overrides = {"cooling_min_percent": "90"}
    current = resolve_profile_settings(current, overrides)
    newer = {**_settings(), "cooling_max_percent": "80"}

    resolved, adjusted = resolve_profile_settings_for_template_update(newer, current, overrides)

    assert resolved["cooling_min_percent"] == "90"
    assert resolved["cooling_max_percent"] == "80"
    assert adjusted == {"cooling_min_percent": "90"}


def test_template_update_preserves_custom_maximum_fan() -> None:
    """A calibrated filament may retain a custom maximum fan speed."""

    base = {**_settings(), "cooling_min_percent": "20"}
    overrides = {"cooling_max_percent": "60"}
    current = resolve_profile_settings(base, overrides)
    newer = {**base, "cooling_min_percent": "70"}

    resolved, adjusted = resolve_profile_settings_for_template_update(newer, current, overrides)

    assert resolved["cooling_min_percent"] == "70"
    assert resolved["cooling_max_percent"] == "60"
    assert adjusted == {"cooling_max_percent": "60"}


def test_template_update_changes_inherited_bed_temperature_but_preserves_override() -> None:
    """A template bed change flows only to profiles that still inherit that field."""

    base = {**_settings(), "bed_temp_c": "60"}
    newer = {**base, "bed_temp_c": "45"}

    inherited, inherited_overrides = resolve_profile_settings_for_template_update(
        newer,
        base,
        {},
    )
    customized, customized_overrides = resolve_profile_settings_for_template_update(
        newer,
        {**base, "bed_temp_c": "70"},
        {"bed_temp_c": "70"},
    )

    assert inherited["bed_temp_c"] == "45"
    assert inherited_overrides == {}
    assert customized["bed_temp_c"] == "70"
    assert customized_overrides == {"bed_temp_c": "70"}


def test_profile_can_override_every_cooling_extension() -> None:
    """Cooling calibration values remain filament-owned through inheritance."""

    base = _settings()
    base_extensions = base["cura_extensions"]
    assert isinstance(base_extensions, dict)
    desired = {
        **base,
        "cooling_enabled": False,
        "cooling_min_percent": "0",
        "cooling_max_percent": "0",
        "cura_extensions": {
            **base_extensions,
            "cool_fan_full_layer": "2",
            "cool_min_layer_time": "6",
            "cool_min_layer_time_fan_speed_max": "12",
            "cool_min_speed": "8",
            "cool_fan_speed_0": "0",
        },
    }

    overrides = sparse_profile_overrides(base, desired)

    assert overrides["cooling_enabled"] is False
    assert overrides["cooling_min_percent"] == "0"
    assert overrides["cooling_max_percent"] == "0"
    assert overrides["cura_extensions"] == {
        "cool_fan_full_layer": "2",
        "cool_fan_speed_0": "0",
        "cool_min_layer_time": "6",
        "cool_min_layer_time_fan_speed_max": "12",
        "cool_min_speed": "8",
    }
