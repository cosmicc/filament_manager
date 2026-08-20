"""Approved Cura Material Settings catalog regression tests."""

from decimal import Decimal
from types import SimpleNamespace

from filament_manager.domain.cura_import import material_settings_from_cura
from filament_manager.domain.cura_material_settings import (
    CURA_EDITABLE_SETTING_KEYS,
    CURA_EXTENSION_SETTING_KEYS,
    CURA_MATERIAL_SETTINGS,
    CURA_TYPED_SETTING_KEYS,
    cura_settings_for_profile,
)


def test_operator_material_settings_catalog_is_exact_and_unique() -> None:
    """Retain the 56 reported settings, with brand/type as derived metadata."""

    keys = [setting.key for setting in CURA_MATERIAL_SETTINGS]

    assert len(keys) == 56
    assert len(set(keys)) == 56
    assert len(CURA_EDITABLE_SETTING_KEYS) == 52
    assert len(CURA_TYPED_SETTING_KEYS) == 24
    assert len(CURA_EXTENSION_SETTING_KEYS) == 29
    assert {setting.key for setting in CURA_MATERIAL_SETTINGS if not setting.editable} == {
        "material_brand",
        "material_type",
        "cool_fan_speed_0",
        "retraction_speed",
    }
    assert {
        "klipper_pressure_advance_factor",
        "klipper_smooth_time_enable",
        "klipper_smooth_time_factor",
    }.issubset(keys)


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
        cura_extensions={
            "klipper_smooth_time_enable": True,
            "klipper_smooth_time_factor": "0.04",
        },
    )

    settings = cura_settings_for_profile(profile)

    assert settings["klipper_pressure_advance_factor"] == "0.035"
    assert settings["klipper_smooth_time_enable"] is True
    assert settings["klipper_smooth_time_factor"] == "0.04"
    assert settings["material_print_temperature"] == "225"
    assert settings["retraction_speed"] == "35"
    assert settings["retraction_retract_speed"] == "35"
    assert settings["retraction_prime_speed"] == "32"
    assert settings["cool_fan_speed_0"] == "0"
    assert settings["cool_fan_speed"] == "70"
    assert settings["cool_fan_speed_max"] == "70"


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
