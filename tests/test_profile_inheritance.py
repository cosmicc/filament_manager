"""Sparse material-profile inheritance tests."""

from filament_manager.domain.profile_inheritance import (
    override_setting_keys,
    resolve_profile_settings,
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

    assert overrides == {
        "extruder_temp_c": "205",
        "cura_extensions": {
            "cool_min_layer_time": None,
            "material_flow_layer_0": "98",
        },
    }
    assert override_setting_keys(overrides) == {
        "extruder_temp_c",
        "cool_min_layer_time",
        "material_flow_layer_0",
    }
    resolved = resolve_profile_settings(base, overrides)
    assert resolved["extruder_temp_c"] == "205"
    assert resolved["flow_percent"] == "100"
    assert resolved["cura_extensions"] == {
        "retraction_enable": True,
        "material_flow_layer_0": "98",
    }


def test_template_update_preserves_filament_overrides() -> None:
    """Moving a base changes inherited values but retains customized values."""

    base = _settings()
    overrides = {"extruder_temp_c": "205", "pressure_advance": "0.13"}
    newer = {**base, "cooling_max_percent": "80", "extruder_temp_c": "210"}

    resolved = resolve_profile_settings(newer, overrides)

    assert resolved["extruder_temp_c"] == "205"
    assert resolved["pressure_advance"] == "0.13"
    assert resolved["cooling_max_percent"] == "80"
