"""Exercise generated Cura overlays at the typed runtime-property boundary."""

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from filament_manager_agent.render import _visibility_plugin_files

PRODUCT_GUID = "00000000-0000-4000-8000-000000000001"
TEMPLATE_GUID = "00000000-0000-4000-8000-000000000002"
PLUGIN_PATH = Path("plugins/FilamentManagerVisibility/FilamentManagerVisibility/FilamentManagerVisibility.py")


class RuntimeMaterial:
    """Expose Cura identity independently of locally edited material values."""

    def __init__(self, guid: str = PRODUCT_GUID, managed: bool = True) -> None:
        self.guid = guid
        self.managed = managed

    def getId(self) -> str:
        return "filament_manager_product" if self.managed else "user_material"

    def getMetaDataEntry(self, key: str, default: str = "") -> str:
        return self.guid if key == "GUID" else default

    def getProperty(self, *_args: object) -> None:
        raise AssertionError("A mutable Cura material must not supply authoritative values")


@pytest.fixture
def runtime_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Any]:
    """Load the complete generated plugin with isolated Cura framework endpoints."""

    definitions = {
        "material_print_temperature": "float",
        "material_flow": "float",
        "retraction_amount": "float",
        "retraction_extrusion_window": "float",
        "retraction_count_max": "int",
        "cool_fan_full_layer": "int",
        "cool_fan_enabled": "bool",
        "unpopulated": "float",
        "choice": "enum",
        "description": "str",
    }
    values = {
        "material_print_temperature": "220.00",
        "material_flow": "98.5",
        "retraction_amount": "0.85",
        "retraction_extrusion_window": "0.85",
        "retraction_count_max": 100,
        "cool_fan_full_layer": "3.000",
        "cool_fan_enabled": False,
        "choice": "standard",
        "description": "220",
    }

    class RuntimeStack:
        """Stand in for the underlying Cura definition and quality layers."""

        def __init__(self) -> None:
            self.material = RuntimeMaterial()
            self.definitions = definitions.copy()
            self.user_value = 17.0

        def getAllKeys(self) -> set[str]:
            return set(self.definitions)

        def getProperty(self, key: str, property_name: str, *args: object, **kwargs: object) -> object:
            if property_name == "type":
                return self.definitions.get(key)
            if property_name == "value":
                return self.user_value
            if property_name == "minimum_value":
                return 0.0
            if property_name == "maximum_value":
                return 300.0
            return (key, property_name, args, kwargs)

    for module_name, class_name, implementation in (
        ("PyQt6.QtCore", "QTimer", object),
        ("UM.Extension", "Extension", object),
        ("UM.Logger", "Logger", object),
        ("cura.Machines.Models.BaseMaterialsModel", "BaseMaterialsModel", object),
        ("cura.Settings.CuraContainerStack", "CuraContainerStack", RuntimeStack),
    ):
        module = ModuleType(module_name)
        setattr(module, class_name, implementation)
        monkeypatch.setitem(sys.modules, module_name, module)

    rendered = _visibility_plugin_files(
        frozenset(definitions),
        frozenset(definitions),
        frozenset(),
        frozenset(),
        {},
        {PRODUCT_GUID: values, TEMPLATE_GUID: {**values, "material_print_temperature": "245.0"}},
    )
    plugin = ModuleType("runtime_material_plugin")
    plugin.__file__ = str(tmp_path / "FilamentManagerVisibility.py")
    # Execute only our renderer's generated code, never a supplied Cura expression.
    exec(compile(rendered[PLUGIN_PATH], plugin.__file__, "exec"), plugin.__dict__)  # noqa: S102
    plugin._install_runtime_material_overlay()
    return plugin, RuntimeStack()


@pytest.mark.parametrize("distance", ["0", "0.85", "6.25"])
def test_managed_values_support_cura_range_checks_and_dependent_arithmetic(
    runtime_overlay: tuple[ModuleType, Any],
    distance: str,
) -> None:
    """Transport strings must behave as numbers in validation and derived settings."""

    plugin, stack = runtime_overlay
    for key in ("retraction_amount", "retraction_extrusion_window"):
        plugin.CANONICAL_MATERIAL_SETTINGS[PRODUCT_GUID][key] = distance
    for key in (
        "material_print_temperature",
        "material_flow",
        "retraction_amount",
        "retraction_extrusion_window",
        "retraction_count_max",
        "cool_fan_full_layer",
    ):
        value = stack.getProperty(key, "value")
        assert stack.getProperty(key, "minimum_value") <= value <= stack.getProperty(key, "maximum_value")
    assert stack.getProperty("material_flow", "value") / 100 == pytest.approx(0.985)
    assert stack.getProperty("retraction_extrusion_window", "value") == float(distance)
    assert stack.getProperty("retraction_amount", "value") == float(distance)
    assert type(stack.getProperty("retraction_count_max", "value")) is int
    assert stack.getProperty("retraction_count_max", "value") == 100
    assert stack.getProperty("cool_fan_full_layer", "value") == 3
    assert stack.getProperty("cool_fan_enabled", "value") is False
    assert stack.getProperty("description", "value") == "220"


@pytest.mark.parametrize(
    ("setting_type", "value", "expected"),
    [
        ("float", "220.00", 220.0),
        ("float", "0", 0.0),
        ("float", "-0.15", -0.15),
        ("float", "3.5e-2", 0.035),
        ("float", 98.5, 98.5),
        ("float", 100, 100.0),
        ("int", "100", 100),
        ("int", "3.000", 3),
        ("int", 0, 0),
        ("bool", False, False),
        ("bool", True, True),
        ("bool", "False", False),
        ("bool", " true ", True),
        ("str", "100", "100"),
        ("enum", "standard", "standard"),
        ("float", "NaN", None),
        ("float", "Infinity", None),
        ("float", "1e999", None),
        ("float", "=speed_print / 2", None),
        ("float", "1 + 2", None),
        ("float", "not a number", None),
        ("float", True, None),
        ("int", "3.5", None),
        ("int", "NaN", None),
        ("bool", "not a boolean", None),
        ("bool", 2, None),
        ("str", 100, None),
        ("unknown", "220", None),
    ],
)
def test_runtime_types_and_invalid_literals(
    runtime_overlay: tuple[ModuleType, Any], setting_type: str, value: object, expected: object
) -> None:
    """Invalid values stay invalid; expressions are never evaluated or replaced by zero."""

    plugin, stack = runtime_overlay
    key = "material_print_temperature"
    stack.definitions[key] = setting_type
    plugin.CANONICAL_MATERIAL_SETTINGS[PRODUCT_GUID][key] = value
    result = stack.getProperty(key, "value")
    assert result == expected
    assert type(result) is type(expected)


def test_overlay_preserves_validation_authority_and_material_switches(
    runtime_overlay: tuple[ModuleType, Any],
) -> None:
    """Enforcement never masks range errors or leaks one material's settings to another."""

    plugin, stack = runtime_overlay
    key = "material_print_temperature"
    context = object()
    assert stack.getProperty(key, "validationState", context=context) == (
        key,
        "validationState",
        (),
        {"context": context},
    )
    plugin.CANONICAL_MATERIAL_SETTINGS[PRODUCT_GUID][key] = "999"
    assert stack.getProperty(key, "value") > stack.getProperty(key, "maximum_value")
    stack.material.guid = TEMPLATE_GUID
    assert stack.getProperty(key, "value") == 245.0
    stack.user_value = 123.0
    assert stack.getProperty(key, "value") == 245.0
    assert stack.getProperty("unpopulated", "value") == 123.0
    assert stack.getProperty("layer_height", "value") == 123.0
    del stack.definitions[key]
    assert stack.getProperty(key, "value") == 123.0
    stack.definitions[key] = "float"
    stack.material.managed = False
    assert stack.getProperty(key, "value") == 123.0
    stack.material.managed = True
    stack.material.guid = "00000000-0000-4000-8000-000000000099"
    assert stack.getProperty(key, "value") == 123.0
