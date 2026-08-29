"""Safe Cura nozzle-variant selection tests."""

from pathlib import Path

import pytest

from filament_manager_agent import nozzle as nozzle_module
from filament_manager_agent.models import CuraInstallation, CuraMachine
from filament_manager_agent.nozzle import apply_nozzle_update, linked_extruder_nozzle_diameter


def _installation(tmp_path: Path) -> CuraInstallation:
    data = tmp_path / "cura" / "5.13"
    machines = data / "machine_instances"
    extruders = data / "extruders"
    definition_changes = data / "definition_changes"
    variants = data / "variants"
    machines.mkdir(parents=True)
    extruders.mkdir()
    definition_changes.mkdir()
    variants.mkdir()
    machine_path = machines / "workshop.global.cfg"
    machine_path.write_text(
        """[general]
name = Workshop Printer
definition = workshop_printer

[metadata]
type = machine
nozzle_diameter = 0.4

[containers]
5 = empty_variant
7 = workshop_printer
""",
        encoding="utf-8",
    )
    (extruders / "workshop_extruder_0.extruder.cfg").write_text(
        """[general]
version = 6
name = Extruder 1
id = workshop_extruder_0

[metadata]
type = extruder_train
position = 0
machine = Workshop Printer
enabled = True

[containers]
5 = workshop_extruder_0_0.4
6 = workshop_extruder_0_settings
7 = workshop_extruder_0
""",
        encoding="utf-8",
    )
    (definition_changes / "workshop_extruder_0_settings.inst.cfg").write_text(
        """[general]
version = 4
name = workshop_extruder_0_settings
definition = workshop_extruder_0

[metadata]
type = definition_changes

[values]
machine_nozzle_size = 0.4
""",
        encoding="utf-8",
    )
    (variants / "workshop_0.6.inst.cfg").write_text(
        """[general]
version = 4
name = Workshop 0.6 mm
definition = workshop_extruder_0

[metadata]
type = variant
hardware_type = nozzle

[values]
machine_nozzle_size = 0.6
""",
        encoding="utf-8",
    )
    return CuraInstallation(
        installation_id="cura-test",
        version="5.13",
        channel="Test",
        data_path=data,
        machines=[
            CuraMachine(
                machine_id="workshop",
                display_name="Workshop Printer",
                definition_id="workshop_printer",
                nozzle_diameter_mm="0.4",
                source_path=machine_path,
            )
        ],
    )


def test_applies_exact_existing_nozzle_variant_with_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installation = _installation(tmp_path)
    monkeypatch.setenv("FILAMENT_MANAGER_AGENT_DATA", str(tmp_path / "agent-data"))

    result = apply_nozzle_update(
        installation,
        "10000000-0000-0000-0000-000000000001",
        {
            "printer_code": "workshop-printer",
            "printer_name": "Workshop Printer",
            "nozzle_diameter_mm": "0.6",
        },
    )

    machine = installation.machines[0].source_path.read_text(encoding="utf-8")
    extruder = (installation.data_path / "extruders" / "workshop_extruder_0.extruder.cfg").read_text(
        encoding="utf-8"
    )
    definition_change = (
        installation.data_path / "definition_changes" / "workshop_extruder_0_settings.inst.cfg"
    ).read_text(encoding="utf-8")
    assert "nozzle_diameter = 0.6" in machine
    assert "FILAMENT_MANAGER_START_PRINT" in machine
    assert "MATERIAL_GUID={material_guid, 0}" in machine
    assert "machine_end_gcode = END_PRINT" in machine
    assert "5 = workshop_0.6" in extruder
    assert "machine_nozzle_size = 0.6" in definition_change
    assert linked_extruder_nozzle_diameter(installation, installation.machines[0]) == "0.6"
    assert result["variant_id"] == "workshop_0.6"
    assert (
        tmp_path / "agent-data" / "nozzle-backups" / "10000000-0000-0000-0000-000000000001" / "cura-test.zip"
    ).is_file()


def test_updates_extruder_nozzle_size_when_no_variant_exists(tmp_path: Path) -> None:
    installation = _installation(tmp_path)

    result = apply_nozzle_update(
        installation,
        "10000000-0000-0000-0000-000000000002",
        {
            "printer_code": "workshop-printer",
            "printer_name": "Workshop Printer",
            "nozzle_diameter_mm": "0.8",
        },
    )

    definition_change = (
        installation.data_path / "definition_changes" / "workshop_extruder_0_settings.inst.cfg"
    ).read_text(encoding="utf-8")
    assert "machine_nozzle_size = 0.8" in definition_change
    assert result["variant_id"] is None


def test_reads_configured_cura_resource_variant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installation = _installation(tmp_path)
    for variant in (installation.data_path / "variants").iterdir():
        variant.unlink()
    resource_root = tmp_path / "cura-resources"
    variants = resource_root / "variants"
    variants.mkdir(parents=True)
    (variants / "workshop_resource_0.6.inst.cfg").write_text(
        """[general]
version = 4
name = Workshop 0.6 mm
definition = workshop_extruder_0

[metadata]
type = variant
hardware_type = nozzle

[values]
machine_nozzle_size = 0.6
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("FILAMENT_MANAGER_CURA_RESOURCE_ROOTS", str(resource_root))
    monkeypatch.setenv("FILAMENT_MANAGER_AGENT_DATA", str(tmp_path / "agent-data"))

    result = apply_nozzle_update(
        installation,
        "10000000-0000-0000-0000-000000000003",
        {
            "printer_code": "workshop-printer",
            "printer_name": "Workshop Printer",
            "nozzle_diameter_mm": "0.6",
        },
    )

    assert result["variant_id"] == "workshop_resource_0.6"


def test_failed_nozzle_update_restores_machine_scripts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installation = _installation(tmp_path)
    monkeypatch.setenv("FILAMENT_MANAGER_AGENT_DATA", str(tmp_path / "agent-data"))
    machine_path = installation.machines[0].source_path
    original_machine = machine_path.read_bytes()
    original_atomic_write = nozzle_module._atomic_write
    failed = False

    def fail_once(target: Path, content: bytes) -> None:
        nonlocal failed
        if not failed and target.parent.name == "extruders":
            failed = True
            raise OSError("simulated nozzle write failure")
        original_atomic_write(target, content)

    monkeypatch.setattr(nozzle_module, "_atomic_write", fail_once)

    with pytest.raises(OSError, match="simulated nozzle write failure"):
        apply_nozzle_update(
            installation,
            "10000000-0000-0000-0000-000000000004",
            {
                "printer_code": "workshop-printer",
                "printer_name": "Workshop Printer",
                "nozzle_diameter_mm": "0.6",
            },
        )

    assert machine_path.read_bytes() == original_machine
