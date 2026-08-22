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


def test_template_update_replaces_legacy_custom_regular_fan() -> None:
    """Cooling values are template owned even when an old profile customized them."""

    current = _settings()
    overrides = {"cooling_min_percent": "90"}
    current = resolve_profile_settings(current, overrides)
    newer = {**_settings(), "cooling_max_percent": "80"}

    resolved, adjusted = resolve_profile_settings_for_template_update(newer, current, overrides)

    assert resolved["cooling_min_percent"] == "50"
    assert resolved["cooling_max_percent"] == "80"
    assert adjusted == {}


def test_template_update_replaces_legacy_custom_maximum_fan() -> None:
    """Both fan range controls inherit from the latest template."""

    base = {**_settings(), "cooling_min_percent": "20"}
    overrides = {"cooling_max_percent": "60"}
    current = resolve_profile_settings(base, overrides)
    newer = {**base, "cooling_min_percent": "70"}

    resolved, adjusted = resolve_profile_settings_for_template_update(newer, current, overrides)

    assert resolved["cooling_min_percent"] == "70"
    assert resolved["cooling_max_percent"] == "100"
    assert adjusted == {}
