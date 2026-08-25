"""Approved Cura Material Settings catalog regression tests."""

from decimal import Decimal
from types import SimpleNamespace

from filament_manager.domain.cura_import import material_settings_from_cura
from filament_manager.domain.cura_material_settings import (
    CURA_ALWAYS_EMITTED_SETTING_VALUES,
    CURA_EDITABLE_SETTING_KEYS,
    CURA_EXTENSION_SETTING_KEYS,
    CURA_MANAGED_SETTING_KEYS,
    CURA_MATERIAL_SETTINGS,
    CURA_RETIRED_SETTING_KEYS,
    CURA_TEMPLATE_ONLY_SETTING_KEYS,
    CURA_TYPED_SETTING_KEYS,
    cura_settings_for_profile,
)


def test_operator_material_settings_catalog_is_exact_and_unique() -> None:
    """Retain the complete unique catalog, including template-only acceleration."""

    keys = [setting.key for setting in CURA_MATERIAL_SETTINGS]

    assert len(keys) == 55
    assert len(set(keys)) == 55
    assert len(CURA_EDITABLE_SETTING_KEYS) == 49
    assert len(CURA_TYPED_SETTING_KEYS) == 25
    assert len(CURA_EXTENSION_SETTING_KEYS) == 26
    assert {setting.key for setting in CURA_MATERIAL_SETTINGS if not setting.editable} == {
        "acceleration_enabled",
        "acceleration_travel_enabled",
        "material_brand",
        "material_type",
        "cool_fan_speed",
        "retraction_speed",
    }
    assert {
        "acceleration_infill",
        "acceleration_print",
        "acceleration_roofing",
        "acceleration_support",
        "acceleration_topbottom",
        "acceleration_travel",
        "acceleration_wall",
        "klipper_smooth_time_enable",
        "klipper_smooth_time_factor",
    }.issubset(keys)
    assert CURA_TEMPLATE_ONLY_SETTING_KEYS == {
        "acceleration_enabled",
        "acceleration_infill",
        "acceleration_print",
        "acceleration_roofing",
        "acceleration_support",
        "acceleration_topbottom",
        "acceleration_travel",
        "acceleration_travel_enabled",
        "acceleration_wall",
        "klipper_smooth_time_enable",
        "klipper_smooth_time_factor",
        "cool_fan_enabled",
        "cool_fan_full_layer",
        "cool_fan_speed_max",
        "cool_fan_speed_min",
        "cool_min_layer_time",
        "cool_min_layer_time_fan_speed_max",
        "cool_min_speed",
        "skirt_brim_speed",
        "speed_infill",
        "speed_layer_0",
        "speed_print",
        "speed_print_layer_0",
        "speed_roofing",
        "speed_support",
        "speed_topbottom",
        "speed_travel",
        "speed_travel_layer_0",
        "speed_wall",
        "speed_wall_0",
        "speed_wall_x",
    }
    assert CURA_ALWAYS_EMITTED_SETTING_VALUES["acceleration_enabled"] is True
    assert CURA_ALWAYS_EMITTED_SETTING_VALUES["acceleration_travel_enabled"] is True
    assert CURA_ALWAYS_EMITTED_SETTING_VALUES.keys() <= CURA_MANAGED_SETTING_KEYS
    assert {
        "default_material_bed_temperature",
        "default_material_print_temperature",
        "ironing_speed",
        "ironing_enabled",
        "limit_support_retractions",
    } <= CURA_RETIRED_SETTING_KEYS
    assert "speed_ironing" in keys
    assert "ironing_speed" not in keys
    assert "ironing_enabled" not in keys
    assert "limit_support_retractions" not in keys


def test_profile_mapping_places_klipper_values_in_the_material_settings() -> None:
    """Pressure advance and smooth time pass through plugin material keys."""

    profile = SimpleNamespace(
        chamber_temp_c=Decimal("35"),
        extruder_temp_c=Decimal("225"),
        bed_temp_c=Decimal("70"),
        flow_percent=Decimal("98.5"),
        print_speed_mm_s=Decimal("160"),
        outer_wall_speed_mm_s=None,
        inner_wall_speed_mm_s=None,
        infill_speed_mm_s=None,
        top_bottom_speed_mm_s=None,
        initial_layer_speed_mm_s=None,
        travel_speed_mm_s=None,
        support_speed_mm_s=None,
        retraction_distance_mm=Decimal("0.8"),
        retraction_speed_mm_s=Decimal("35"),
        retraction_prime_speed_mm_s=Decimal("32"),
        cooling_enabled=True,
        cooling_min_percent=Decimal("30"),
        cooling_max_percent=Decimal("70"),
        support_overhang_angle_deg=Decimal("55"),
        pressure_advance=Decimal("0.035"),
        ironing_flow_percent=Decimal("11"),
        ironing_speed_mm_s=Decimal("25"),
        ironing_line_spacing_mm=Decimal("0.12"),
        cura_extensions={
            "acceleration_print": "5000",
            "acceleration_travel": "8000",
            "klipper_smooth_time_enable": True,
            "klipper_smooth_time_factor": "0.04",
            "cool_fan_speed_0": "15",
            "limit_support_retractions": True,
        },
    )

    settings = cura_settings_for_profile(profile)

    assert settings["klipper_pressure_advance_factor"] == "0.035"
    assert settings["klipper_smooth_time_enable"] is True
    assert settings["klipper_smooth_time_factor"] == "0.04"
    assert settings["acceleration_enabled"] is True
    assert settings["acceleration_travel_enabled"] is True
    assert settings["acceleration_print"] == "5000"
    assert settings["acceleration_travel"] == "8000"
    assert settings["material_print_temperature"] == "225"
    assert settings["material_bed_temperature"] == "70"
    assert "default_material_print_temperature" not in settings
    assert "default_material_bed_temperature" not in settings
    assert settings["retraction_speed"] == "35"
    assert settings["retraction_retract_speed"] == "35"
    assert settings["retraction_prime_speed"] == "32"
    assert settings["cool_fan_speed_0"] == "15"
    assert settings["cool_fan_speed"] == "70"
    assert settings["cool_fan_speed_max"] == "70"
    assert settings["speed_ironing"] == "25"
    assert "limit_support_retractions" not in settings


def test_cura_aliases_resolve_to_one_canonical_setting_without_extension_overlap() -> None:
    """Cura child aliases import through one canonical application control."""

    settings = material_settings_from_cura(
        {
            "material_print_temperature": "210",
            "material_bed_temperature": "60",
            "retraction_retract_speed": "42",
            "retraction_prime_speed": "38",
            "cool_fan_speed_max": "80",
        },
        filament_density_g_cm3=Decimal("1.24"),
        preferred_build_plate_surface_id=None,
    )

    assert settings["retraction_speed_mm_s"] == Decimal("42")
    assert settings["retraction_prime_speed_mm_s"] == Decimal("38")
    assert settings["cooling_max_percent"] == Decimal("80")
    assert "retraction_retract_speed" not in settings["cura_extensions"]
    assert "retraction_prime_speed" not in settings["cura_extensions"]
    assert "cool_fan_speed_max" not in settings["cura_extensions"]


def test_prime_speed_import_does_not_remove_the_existing_retract_speed() -> None:
    """Retract and prime speeds remain independent while merging Cura edits."""

    from filament_manager.domain.cura_import import merge_cura_settings

    merged = merge_cura_settings(
        {"retraction_retract_speed": "42", "retraction_prime_speed": "42"},
        {"retraction_prime_speed": "37"},
    )

    assert merged["retraction_retract_speed"] == "42"
    assert merged["retraction_prime_speed"] == "37"
