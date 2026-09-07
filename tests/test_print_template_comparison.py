"""Historical comparisons preserve evidence and distinguish unknown from unchanged."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from filament_manager.api.schemas import MaterialSettingsInput
from filament_manager.domain.profile_inheritance import normalize_settings, resolve_profile_settings
from filament_manager.services.print_template_comparison import (
    compare_print_settings,
    current_print_template_comparison,
)


def test_current_comparison_includes_motion_and_ignores_care_metadata() -> None:
    """Template-only print values still matter, and numeric formatting does not."""

    used = normalize_settings(
        {
            "extruder_temp_c": "210.000",
            "print_speed_mm_s": "60",
            "cura_extensions": {"acceleration_print": "1000"},
        }
    )
    saved = deepcopy(used)
    current = {
        **used,
        "extruder_temp_c": 210,
        "print_speed_mm_s": "80",
        "drying_time_hours": "12+",
        "moisture_sensitivity": "extremely high",
        "cura_extensions": {"acceleration_print": "1500"},
    }
    result = compare_print_settings(used, current)
    assert result.status == "differs"
    assert {item.key for item in result.differences} == {
        "print_speed_mm_s",
        "cura_extensions.acceleration_print",
    }
    assert used == saved
    assert compare_print_settings(used, {**used, "drying_temp_c": "80"}).status == "matches"


def test_missing_history_is_partial_even_when_known_values_match() -> None:
    """A sparse legacy document must never be presented as a complete match."""

    result = compare_print_settings({"extruder_temp_c": "210"}, {"extruder_temp_c": 210})
    assert result.status == "partial"
    assert result.differences == []
    assert "bed_temp_c" in result.missing_keys
    assert "cura_extensions" in result.missing_keys


@pytest.mark.asyncio
async def test_unresolved_and_invalid_template_identity_do_not_query_database() -> None:
    """An absent original link cannot be replaced by a filament's current template."""

    session = AsyncMock()
    for snapshot in ({}, {"managed": {"resolved": {"bed_temp_c": "50"}, "template": {"id": "bad"}}}):
        assert (await current_print_template_comparison(session, snapshot)).status == "unavailable"
    session.execute.assert_not_awaited()


def test_care_options_are_validated_and_remain_template_owned() -> None:
    """Care strings survive normalization and cannot become profile overrides."""

    base = {
        "extruder_temp_c": "210",
        "bed_temp_c": "60",
        "flow_percent": "100",
        "cooling_min_percent": "0",
        "cooling_max_percent": "100",
        "filament_density_g_cm3": "1.24",
        "drying_time_hours": "6-8",
        "moisture_sensitivity": "high-moderate",
    }
    assert MaterialSettingsInput.model_validate(base).drying_time_hours == "6-8"
    for key, value in (("drying_time_hours", "forever"), ("moisture_sensitivity", "unknown")):
        with pytest.raises(ValidationError):
            MaterialSettingsInput.model_validate({**base, key: value})
    resolved = resolve_profile_settings(base, {"drying_time_hours": "12+", "moisture_sensitivity": "low"})
    assert resolved["drying_time_hours"] == "6-8"
    assert resolved["moisture_sensitivity"] == "high-moderate"
