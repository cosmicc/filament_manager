"""Atomic hardness validation, inheritance, reversion and outbound isolation."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from filament_manager.api.schemas import MaterialSettingsInput, ShoreHardness
from filament_manager.domain.cura_material_settings import cura_settings_for_profile
from filament_manager.domain.profile_inheritance import (
    profile_columns_from_settings,
    resolve_profile_settings,
    resolve_profile_settings_for_template_update,
    sparse_profile_overrides,
)


@pytest.mark.parametrize(
    "value",
    [
        {"scale": "B", "value": 95},
        {"scale": "A", "value": -1},
        {"scale": "D", "value": 101},
        {"scale": "D", "value": True},
        {"scale": "A", "value": "NaN"},
        {"scale": "A", "value": "1.234"},
        {"scale": "A"},
        {"value": 90},
        {"scale": "A", "value": 95, "D": 45},
    ],
)
def test_invalid_hardness_is_rejected(value: dict[str, object]) -> None:
    """Accept exactly one valid scale/value pair, with no hidden second measurement."""
    with pytest.raises(ValidationError):
        ShoreHardness.model_validate(value)


def test_atomic_inheritance_override_clear_and_revert() -> None:
    """A customized A measurement survives a D template change as a complete pair."""
    base = {"shore_hardness": {"scale": "A", "value": "90"}}
    before = deepcopy(base)
    desired = {"shore_hardness": {"scale": "A", "value": "95"}}
    overrides = sparse_profile_overrides(base, desired)
    newer = {"shore_hardness": {"scale": "D", "value": "75"}}
    resolved, retained = resolve_profile_settings_for_template_update(newer, desired, overrides)
    assert resolved["shore_hardness"] == desired["shore_hardness"]
    assert retained == overrides
    assert resolve_profile_settings(newer, {})["shore_hardness"] == newer["shore_hardness"]
    assert sparse_profile_overrides(base, {"shore_hardness": {"scale": "A", "value": 90.0}}) == {}
    cleared = sparse_profile_overrides(base, {"shore_hardness": None})
    assert cleared == {"shore_hardness": None}
    assert resolve_profile_settings(newer, cleared)["shore_hardness"] is None
    assert profile_columns_from_settings(desired)["shore_hardness"] == desired["shore_hardness"]
    assert base == before


def test_hardness_does_not_enter_cura_settings() -> None:
    """Reference metadata cannot change Cura settings or become a heater command."""
    required = {
        "extruder_temp_c": 210,
        "bed_temp_c": 60,
        "flow_percent": 100,
        "cooling_min_percent": 0,
        "cooling_max_percent": 100,
        "filament_density_g_cm3": "1.24",
    }
    blank = MaterialSettingsInput(**required)
    populated = MaterialSettingsInput(**required, shore_hardness={"scale": "D", "value": "75"})
    assert cura_settings_for_profile(blank) == cura_settings_for_profile(populated)
    assert populated.model_dump(mode="json")["shore_hardness"] == {"scale": "D", "value": "75"}
