"""Cura recovery capture, secret filtering, and atomic restore tests."""

import json
from pathlib import Path

import pytest

from filament_manager_agent.models import CuraInstallation
from filament_manager_agent.recovery import (
    capture_recovery_snapshot,
    material_settings_plugin_inventory,
    restore_recovery_snapshot,
)
from filament_manager_agent.service import _recovery_capture_message


def _installation(data_root: Path, config_root: Path) -> CuraInstallation:
    data_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)
    return CuraInstallation(
        installation_id="cura-test",
        version="5.13",
        channel="Test Cura",
        data_path=data_root,
        config_path=config_root,
        setting_version=27,
    )


def _write_operational_settings(installation: CuraInstallation, *, theme: str = "dark") -> None:
    machine_directory = installation.data_path / "machine_instances"
    extruder_directory = installation.data_path / "extruders"
    definition_change_directory = installation.data_path / "definition_changes"
    quality_directory = installation.data_path / "quality_changes"
    machine_directory.mkdir()
    extruder_directory.mkdir()
    definition_change_directory.mkdir()
    quality_directory.mkdir()
    (machine_directory / "Workshop.global.cfg").write_text(
        """[general]
version = 4
name = Workshop Printer
id = workshop

[metadata]
type = machine
setting_version = 27

[values]
machine_start_gcode = G28
machine_end_gcode = M84
machine_width = 260
machine_depth = 260
server_url = https://private-printer.example
api_key = never-upload-this
apiKey = never-upload-this-either
cache_file = /srv/private-cura-cache
""",
        encoding="utf-8",
    )
    (extruder_directory / "workshop_extruder_0.extruder.cfg").write_text(
        """[general]
version = 6
name = Extruder 1

[metadata]
type = extruder_train
position = 0
machine = Workshop Printer

[containers]
5 = workshop_0.6
6 = workshop_extruder_0_settings
7 = workshop_extruder_0
""",
        encoding="utf-8",
    )
    (definition_change_directory / "workshop_extruder_0_settings.inst.cfg").write_text(
        """[general]
version = 4
name = workshop_extruder_0_settings
definition = workshop_extruder_0

[metadata]
type = definition_changes

[values]
machine_nozzle_size = 0.6
machine_heat_zone_length = 16
""",
        encoding="utf-8",
    )
    (quality_directory / "Workshop_standard.inst.cfg").write_text(
        """[general]
version = 4
name = Workshop Standard
definition = fdmprinter

[metadata]
type = quality_changes
setting_version = 27

[values]
layer_height = 0.2
""",
        encoding="utf-8",
    )
    assert installation.config_path is not None
    moonraker_instances = json.dumps(
        {
            "workshop": {
                "url": "https://private-printer.example",
                "api_key": "never-upload-plugin-token",
                "upload_dialog": True,
                "upload_start_print_job": False,
                "output_format": "ufp",
            }
        },
        separators=(",", ":"),
    )
    (installation.config_path / "cura.cfg").write_text(
        f"""[general]
theme = {theme}
ultimaker_auth_data = never-upload-account-token

[cura]
active_machine = workshop

[moonraker]
server_url = https://private-printer.example
api_key = never-upload-plugin-token
instances = {moonraker_instances}

[material_settings]
show_all = True
""",
        encoding="utf-8",
    )
    (installation.data_path / "packages.json").write_text(
        json.dumps(
            {
                "installed": {
                    "MaterialSettingsPlugin": {
                        "filename": "/private/download/path",
                        "package_info": {
                            "display_name": "Material Settings",
                            "package_version": "4.3.1",
                            "website": "https://marketplace.example",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (installation.config_path / "plugins.json").write_text(
        json.dumps({"disabled": [], "to_install": [], "to_remove": []}),
        encoding="utf-8",
    )


def test_capture_keeps_operational_settings_but_excludes_secrets_and_paths(tmp_path: Path) -> None:
    installation = _installation(tmp_path / "data" / "5.13", tmp_path / "config" / "5.13")
    _write_operational_settings(installation)

    snapshot = capture_recovery_snapshot(installation)
    serialized = json.dumps(snapshot, sort_keys=True)

    assert snapshot["snapshot_checksum"]
    assert "Workshop Printer" in serialized
    assert "Workshop Standard" in serialized
    assert "machine_start_gcode" in serialized
    assert "machine_end_gcode" in serialized
    assert "machine_width" in serialized
    assert "machine_nozzle_size" in serialized
    assert "machine_heat_zone_length" in serialized
    assert "Material Settings" in serialized
    assert "never-upload" not in serialized
    assert "https://" not in serialized
    assert "/private/download/path" not in serialized
    assert "/srv/private-cura-cache" not in serialized
    assert "moonraker" in serialized.casefold()
    assert "upload_dialog" in serialized
    assert "upload_start_print_job" in serialized


def test_capture_accepts_cura_setting_visibility_bare_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cura visibility presets use valid key-only lines instead of key/value pairs."""

    installation = _installation(tmp_path / "data" / "5.13", tmp_path / "config" / "5.13")
    _write_operational_settings(installation)
    visibility_directory = installation.data_path / "setting_visibility"
    visibility_directory.mkdir()
    (visibility_directory / "workshop.cfg").write_text(
        """[general]
name = Workshop
weight = 0
version = 2

[resolution]
layer_height
layer_height_0

[material]
material_print_temperature
material_flow
""",
        encoding="utf-8",
    )

    snapshot = capture_recovery_snapshot(installation)
    visibility = next(
        item
        for item in snapshot["payload"]["files"]  # type: ignore[index,union-attr]
        if item["relative_path"] == "setting_visibility/workshop.cfg"
    )

    assert "layer_height\n" in visibility["content"]
    assert "material_print_temperature\n" in visibility["content"]

    target = _installation(tmp_path / "restored-data" / "5.13", tmp_path / "restored-config" / "5.13")
    monkeypatch.setenv("FILAMENT_MANAGER_AGENT_DATA", str(tmp_path / "agent-data"))
    restore_recovery_snapshot(
        target,
        "10000000-0000-0000-0000-000000000002",
        str(snapshot["snapshot_checksum"]),
        snapshot["payload"],  # type: ignore[arg-type]
    )

    restored = (target.data_path / "setting_visibility" / "workshop.cfg").read_text(encoding="utf-8")
    assert "layer_height\n" in restored
    assert "material_print_temperature\n" in restored


def test_recovery_capture_errors_have_actionable_path_free_messages() -> None:
    """The workstation page explains the failure class without exposing local paths."""

    message = _recovery_capture_message(RuntimeError("A supported Cura configuration file is invalid."))

    assert message == "A supported Cura settings file contains invalid syntax."
    assert "/" not in message


def test_reports_required_material_plugin_version_and_enabled_state(tmp_path: Path) -> None:
    """Heartbeat metadata identifies the installed required Cura plugin package."""

    installation = _installation(tmp_path / "data" / "5.13", tmp_path / "config" / "5.13")
    _write_operational_settings(installation)

    assert material_settings_plugin_inventory(installation) == [
        {
            "role": "material_settings",
            "package_id": "MaterialSettingsPlugin",
            "display_name": "Material Settings",
            "version": "4.3.1",
            "enabled": True,
        }
    ]


def test_restore_replaces_profiles_and_merges_preferences_without_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _installation(tmp_path / "source-data" / "5.13", tmp_path / "source-config" / "5.13")
    _write_operational_settings(source, theme="dark")
    snapshot = capture_recovery_snapshot(source)

    target = _installation(tmp_path / "target-data" / "5.13", tmp_path / "target-config" / "5.13")
    (target.data_path / "machine_instances").mkdir()
    (target.data_path / "machine_instances" / "Reset.global.cfg").write_text(
        "[general]\nname = Reset Printer\n",
        encoding="utf-8",
    )
    assert target.config_path is not None
    (target.config_path / "cura.cfg").write_text(
        """[general]
theme = light
ultimaker_auth_data = keep-current-login-token

[moonraker]
server_url = https://current-printer.example
api_key = keep-current-plugin-token
instances = {"workshop":{"url":"https://current-printer.example","api_key":"keep-current-plugin-token","upload_dialog":false,"upload_start_print_job":true}}
""",
        encoding="utf-8",
    )
    agent_data = tmp_path / "agent-data"
    monkeypatch.setenv("FILAMENT_MANAGER_AGENT_DATA", str(agent_data))

    result = restore_recovery_snapshot(
        target,
        "10000000-0000-0000-0000-000000000001",
        str(snapshot["snapshot_checksum"]),
        snapshot["payload"],  # type: ignore[arg-type]
    )

    assert result["status"] == "restored"
    assert not (target.data_path / "machine_instances" / "Reset.global.cfg").exists()
    restored_machine = target.data_path / "machine_instances" / "Workshop.global.cfg"
    assert restored_machine.is_file()
    assert "Workshop Printer" in restored_machine.read_text(encoding="utf-8")
    assert "machine_start_gcode = G28" in restored_machine.read_text(encoding="utf-8")
    assert "machine_end_gcode = M84" in restored_machine.read_text(encoding="utf-8")
    assert "machine_width = 260" in restored_machine.read_text(encoding="utf-8")
    restored_extruder_settings = (
        target.data_path / "definition_changes" / "workshop_extruder_0_settings.inst.cfg"
    ).read_text(encoding="utf-8")
    assert "machine_nozzle_size = 0.6" in restored_extruder_settings
    assert "machine_heat_zone_length = 16" in restored_extruder_settings
    preferences = (target.config_path / "cura.cfg").read_text(encoding="utf-8")
    assert "theme = dark" in preferences
    assert "keep-current-login-token" in preferences
    assert "https://current-printer.example" in preferences
    assert "keep-current-plugin-token" in preferences
    assert '"upload_dialog":true' in preferences
    assert '"upload_start_print_job":false' in preferences
    assert (
        agent_data / "recovery-backups" / "10000000-0000-0000-0000-000000000001" / "cura-test.zip"
    ).is_file()


def test_capture_rejects_supported_directory_symlink(tmp_path: Path) -> None:
    installation = _installation(tmp_path / "data" / "5.13", tmp_path / "config" / "5.13")
    outside = tmp_path / "outside"
    outside.mkdir()
    (installation.data_path / "machine_instances").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="directory is unsafe"):
        capture_recovery_snapshot(installation)
