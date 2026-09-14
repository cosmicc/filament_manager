"""Regression coverage for 0.8.3 safety, scheduling, and concurrency boundaries."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from filament_manager.domain.gcode_inspection import inspect_gcode
from filament_manager.domain.gcode_observations import GcodeObservations
from filament_manager.domain.printer_settings import printer_settings_token
from filament_manager.models.enums import GcodeInspectionStatus
from filament_manager.models.printing import PrintJob
from filament_manager.services import database_backups
from filament_manager.services.print_history import _blocking_gate_passed


def test_streamed_heater_maxima_and_adaptive_layers() -> None:
    """Later tower heating and layer changes survive arbitrary download chunks."""
    stream = GcodeObservations()
    data = (
        b"M104 S210\nM190 S60\n;LAYER:0\nG0 Z0.3\nG1 X1 E1\n"
        b";LAYER:1\nG0 Z0.5\nG1 X2 E2\n;LAYER:2\nG0 Z0.65\nG1 X3 E3\n"
        b"M109 T0 S310\nM140 S130\nM191 S40\n"
    )
    for index in range(0, len(data), 7):
        stream.feed(data[index : index + 7])
    values = stream.finish()
    assert Decimal(values["initial_layer_height_mm"]) == Decimal("0.3")
    assert Decimal(values["minimum_layer_height_mm"]) == Decimal("0.15")
    assert Decimal(values["maximum_layer_height_mm"]) == Decimal("0.2")
    result = inspect_gcode(
        {"stream_observations": values},
        "",
        "",
        expected_profile=None,
        expected_material_guid=None,
        expected_machine_name=None,
        expected_extruder_temp_limit_c="300",
        expected_bed_temp_limit_c="120",
        require_chamber_when_configured=False,
    )
    assert {item["field"] for item in result.mismatches} == {
        "maximum_extruder_temp_c",
        "maximum_bed_temp_c",
        "maximum_chamber_temp_c",
    }
    assert all(item["blocking"] for item in result.mismatches)


def test_initial_bed_limit_is_checked_even_with_lower_regular_temperature() -> None:
    result = inspect_gcode(
        {},
        "FILAMENT_MANAGER_START_PRINT BED_TEMP=130 REGULAR_BED_TEMP=60 EXTRUDER_TEMP=200",
        "",
        expected_profile=None,
        expected_material_guid=None,
        expected_machine_name=None,
        expected_bed_temp_limit_c="120",
    )
    assert any(item["field"] == "initial_bed_temp_c" and item["blocking"] for item in result.mismatches)


def test_heater_comments_and_oversized_lines_never_become_commands() -> None:
    stream = GcodeObservations()
    stream.feed(b";M109 S999\n" + b"x" * 5000 + b"M109 S999\nM104 S220\n")
    assert stream.finish() == {"maximum_extruder_temp_c": "220"}


def test_absurd_heater_target_is_retained_as_unsafe_not_discarded() -> None:
    stream = GcodeObservations()
    stream.feed(b"M109 S999999999999999999999999999999999\n")
    result = inspect_gcode(
        {"stream_observations": stream.finish()},
        "",
        "",
        expected_profile=None,
        expected_material_guid=None,
        expected_machine_name=None,
        expected_extruder_temp_limit_c="300",
    )
    assert any(item.get("blocking") for item in result.mismatches)


def test_warn_mode_cannot_release_hardware_failure() -> None:
    job = PrintJob(
        inspection_policy="warn",
        inspection_status=GcodeInspectionStatus.WARNING,
        inspected_at=datetime.now(UTC),
        inspection={"mismatches": [{"field": "flow_percent"}]},
    )
    assert _blocking_gate_passed(job)
    job.inspection = {"mismatches": [{"blocking": True}]}
    assert not _blocking_gate_passed(job)
    job.inspection = {"mismatches": ["invalid evidence"]}
    assert not _blocking_gate_passed(job)


def test_printer_settings_token_ignores_telemetry_but_detects_edits() -> None:
    printer = SimpleNamespace(name="Printer", max_bed_temp_c=Decimal("100"), status="idle", record_version=1)
    token = printer_settings_token(printer)
    printer.record_version = 8
    printer.status = "printing"
    assert printer_settings_token(printer) == token
    printer.max_bed_temp_c = Decimal("120")
    assert printer_settings_token(printer) != token


@pytest.mark.asyncio
async def test_missed_backups_coalesce_and_new_occurrence_supersedes_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    policy = database_backups.BackupPolicy(interval_hours=1)
    monkeypatch.setattr(database_backups, "get_backup_policy", AsyncMock(return_value=policy))
    monkeypatch.setattr(
        database_backups,
        "list_backup_archives",
        lambda: [SimpleNamespace(storage_kind="automatic", created_at=now - timedelta(hours=8, minutes=5))],
    )
    monkeypatch.setattr(
        database_backups,
        "backup_status",
        lambda: {
            "checked_at": (now - timedelta(hours=2)).isoformat(),
            "next_retry_at": (now + timedelta(hours=2)).isoformat(),
        },
    )
    monkeypatch.setattr(database_backups, "backup_has_active_print", AsyncMock(return_value=False))
    assert (await database_backups.backup_is_due(AsyncMock()))[0]
    monkeypatch.setattr(database_backups, "backup_has_active_print", AsyncMock(return_value=True))
    assert not (await database_backups.backup_is_due(AsyncMock()))[0]
    monkeypatch.setattr(database_backups, "backup_has_active_print", AsyncMock(return_value=False))
    monkeypatch.setattr(
        database_backups,
        "list_backup_archives",
        lambda: [SimpleNamespace(storage_kind="automatic", created_at=now)],
    )
    assert not (await database_backups.backup_is_due(AsyncMock()))[0]
