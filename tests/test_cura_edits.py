"""Managed Cura edit scope tests."""

from filament_manager.services.cura_edits import merge_editable_cura_settings


def test_product_cura_edits_preserve_template_only_and_derived_values() -> None:
    """A product material cannot turn template or derived values into overrides."""

    expected = {
        "material_print_temperature": "220",
        "speed_print": "100",
        "acceleration_enabled": True,
        "cool_fan_speed": "80",
    }

    merged = merge_editable_cura_settings(
        expected,
        {
            "material_print_temperature": "225",
            "speed_print": "150",
            "acceleration_enabled": False,
            "cool_fan_speed": "40",
        },
        source_kind="product",
    )

    assert merged == {
        "material_print_temperature": "225",
        "speed_print": "100",
        "acceleration_enabled": True,
        "cool_fan_speed": "80",
    }


def test_template_cura_edits_accept_template_only_but_preserve_derived_values() -> None:
    """A Template material owns template controls but not forced or alias controls."""

    expected = {
        "speed_print": "100",
        "acceleration_enabled": True,
        "cool_fan_speed": "80",
    }

    merged = merge_editable_cura_settings(
        expected,
        {
            "speed_print": "150",
            "acceleration_enabled": False,
            "cool_fan_speed": "40",
        },
        source_kind="template",
    )

    assert merged == {
        "speed_print": "150",
        "acceleration_enabled": True,
        "cool_fan_speed": "80",
    }
