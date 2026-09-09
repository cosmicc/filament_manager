"""0.8.1 retained evidence and bounded external duration contracts."""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.models.printing import PrintJob
from filament_manager.services.print_setting_evidence import retained_setting_summary


def test_retained_settings_fill_gaps_without_rewriting_history() -> None:
    job = PrintJob(
        profile_snapshot={
            "bed_temp_c": "60.12345",
            "flow_percent": "0",
            "print_speed_mm_s": "speed_print * 2",
            "retraction_distance_mm": "2.54321",
            "extruder_temp_c": "205",
            "pressure_advance": "NaN",
        },
        extruder_temp_c=Decimal("210"),
    )
    original = deepcopy(job.profile_snapshot)
    values = retained_setting_summary(job)
    assert values["bed_temp_c"] == Decimal("60.12345")
    assert values["flow_percent"] == 0
    assert values["retraction_distance_mm"] == Decimal("2.54321")
    assert "extruder_temp_c" not in values
    assert "initial_bed_temp_c" not in values
    assert "pressure_advance" not in values and "print_speed_mm_s" not in values
    assert values["setting_sources"]["bed_temp_c"] == "captured_profile"
    assert values["setting_sources"]["extruder_temp_c"] == "recorded_print"
    assert job.profile_snapshot == original and job.bed_temp_c is None


@pytest.mark.asyncio
@pytest.mark.parametrize("total,longest", [("1234.56789", "345.6789"), ("0", "0")])
async def test_moonraker_duration_totals_preserve_exact_source_values(total: str, longest: str) -> None:
    client = object.__new__(MoonrakerClient)
    client._get = AsyncMock(
        return_value={
            "result": {
                "job_totals": {"total_print_time": total, "longest_print": longest, "total_time": "999999"}
            }
        }
    )
    assert await client.history_totals() == (Decimal(total), Decimal(longest))
    client._get.assert_awaited_once_with("/server/history/totals")


@pytest.mark.asyncio
@pytest.mark.parametrize("total,longest", [(True, 1), ("NaN", 1), (-1, 0), (5, 6), ("1e99", 1)])
async def test_malformed_history_totals_fail_closed(total: object, longest: object) -> None:
    client = object.__new__(MoonrakerClient)
    client._get = AsyncMock(
        return_value={"result": {"job_totals": {"total_print_time": total, "longest_print": longest}}}
    )
    with pytest.raises(MoonrakerError):
        await client.history_totals()
