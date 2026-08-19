"""Transactional Cura rendering and installation tests."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from filament_manager_agent.apply import apply_rendered, managed_library_checksum, rollback
from filament_manager_agent.discovery import (
    discover_installations,
    discover_managed_materials,
    discover_materials,
    discover_print_profiles,
)
from filament_manager_agent.render import render_deployment
from filament_manager_agent.service import heartbeat_payload


def _cura_fixture(tmp_path: Path, monkeypatch: object) -> Path:
    root = tmp_path / "cura"
    version = root / "5.10"
    (version / "machine_instances").mkdir(parents=True)
    (version / "definition_changes").mkdir()
    (version / "machine_instances" / "flsun-v400.global.cfg").write_text(
        """[general]
version = 4
name = FLSUN V400
definition = flsun_v400

[metadata]
type = machine
setting_version = 27
nozzle_diameter = 0.4

[containers]
3 = fast
7 = flsun_v400
""",
        encoding="utf-8",
    )
    (version / "definition_changes" / "flsun-v400_settings.inst.cfg").write_text(
        """[general]
version = 4
name = FLSUN V400 settings
definition = flsun_v400

[metadata]
type = definition_changes
setting_version = 27

[values]
machine_start_gcode = G28\n\tBED_MESH_PROFILE LOAD=P1
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("FILAMENT_MANAGER_CURA_ROOTS", str(root))
    monkeypatch.setenv("FILAMENT_MANAGER_AGENT_DATA", str(tmp_path / "agent-data"))
    return version


def _payload() -> dict[str, object]:
    entry = {
        "source_kind": "product",
        "source_id": "84e0fe98-5994-4c14-aafb-8bb8220b0b9c",
        "cura_material_guid": "00000000-0000-4000-8000-000000000001",
        "profile": {
            "id": "84e0fe98-5994-4c14-aafb-8bb8220b0b9c",
            "version": 2,
            "checksum": "a" * 64,
            "settings": {
                "material_print_temperature": "220",
                "material_bed_temperature": "70",
                "material_flow": "98.5",
                "speed_print": "180",
                "cool_fan_enabled": True,
                "cool_fan_speed": "60",
                "support_angle": "55",
                "klipper_pressure_advance_factor": "0.035",
                "klipper_smooth_time_enable": True,
            },
        },
        "material": {
            "product_id": "d1e1d7ce-f0bc-46f5-86b2-d2c74f272f00",
            "brand": "Polymaker",
            "material_type": "PETG",
            "product_name": "PolyLite PETG",
            "color_name": "Black",
            "filler": None,
            "finish": "Silk",
            "color_hex": "#111111",
            "diameter_mm": "1.75",
            "density_g_cm3": "1.27",
            "nominal_net_mass_g": "1000",
        },
        "printer": {
            "id": "312e2722-e60b-467e-8807-cfe410555bee",
            "code": "flsun-v400",
            "name": "FLSUN V400",
            "nozzle_diameter_mm": "0.4",
        },
        "preferred_build_plate": {
            "code": "P1",
            "physical_plate_code": "P1",
            "side": "a",
            "name": "Textured PEI",
            "surface_material": "PEI",
            "texture": "textured",
        },
    }
    return {
        "schema_version": 3,
        "hide_bundled_materials": True,
        "managed_material_setting_keys": [
            "cool_fan_enabled",
            "cool_fan_speed",
            "klipper_pressure_advance_factor",
            "klipper_smooth_time_enable",
            "material_bed_temperature",
            "material_flow",
            "material_print_temperature",
            "speed_print",
            "support_angle",
        ],
        "library_checksum": "a" * 64,
        "materials": [entry],
    }


def test_discovers_and_renders_complete_profile(tmp_path: Path, monkeypatch: object) -> None:
    _cura_fixture(tmp_path, monkeypatch)
    installations = discover_installations()
    assert len(installations) == 1
    assert installations[0].setting_version == 27
    assert installations[0].machines[0].quality_definition_id == "fdmprinter"
    assert installations[0].machines[0].quality_type == "fast"
    rendered = render_deployment(installations[0], _payload())
    paths = {path.as_posix() for path in rendered.files}
    assert len(paths) == 4
    material_path = next(path for path in paths if path.startswith("materials/"))
    material_file = rendered.files[Path(material_path)]
    assert b'key="klipper_pressure_advance_factor">0.035' in material_file
    assert b'key="klipper_smooth_time_enable">True' in material_file
    assert b'key="speed_print">180' in material_file
    assert b"<GUID>00000000-0000-4000-8000-000000000001</GUID>" in material_file
    assert b"<description>Filament Filler: None\nFilament Finish: Silk</description>" in material_file
    assert not any(path.startswith("quality_changes/") for path in paths)
    assert not any(path.startswith("definition_changes/") for path in paths)
    assert "plugins/FilamentManagerVisibility/FilamentManagerVisibility/plugin.json" in paths
    plugin_path = Path(
        "plugins/FilamentManagerVisibility/FilamentManagerVisibility/FilamentManagerVisibility.py"
    )
    plugin = rendered.files[plugin_path]
    plugin_init = rendered.files[
        Path("plugins/FilamentManagerVisibility/FilamentManagerVisibility/__init__.py")
    ]
    compile(plugin, str(plugin_path), "exec")
    assert b"FilamentManagerVisibility(app)" in plugin_init
    assert b'preferences.setValue("cura/favorite_materials", updated)' in plugin
    assert b'preferences.setValue("material_settings/visible_settings", expected)' in plugin
    assert b'"speed_print"' not in plugin
    assert b"'speed_print'" in plugin
    assert b'user_changes.setProperty(key, "value", material_value)' in plugin


def test_generated_plugin_defers_machine_manager_until_cura_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plugin registration must not start active-machine restoration during loading."""

    _cura_fixture(tmp_path, monkeypatch)
    rendered = render_deployment(discover_installations()[0], _payload())
    plugin_path = Path(
        "plugins/FilamentManagerVisibility/FilamentManagerVisibility/FilamentManagerVisibility.py"
    )
    plugin = rendered.files[plugin_path]

    class FakeSignal:
        def __init__(self) -> None:
            self.callbacks: list[object] = []

        def connect(self, callback: object) -> None:
            self.callbacks.append(callback)

        def emit(self) -> None:
            for callback in self.callbacks:
                callback()  # type: ignore[operator]

    class FakeTimer:
        @staticmethod
        def singleShot(_delay: int, callback: object) -> None:
            callback()  # type: ignore[operator]

    class FakeExtension:
        pass

    class FakeLogger:
        @staticmethod
        def log(*_args: object) -> None:
            return None

        @staticmethod
        def logException(*_args: object) -> None:
            return None

    class FakeBaseMaterialsModel:
        def _update(self) -> None:
            return None

    class FakeMachineManager:
        def __init__(self) -> None:
            for name in (
                "activeMaterialChanged",
                "activeQualityChanged",
                "activeQualityChangesGroupChanged",
                "activeStackChanged",
                "globalContainerChanged",
            ):
                setattr(self, name, FakeSignal())

    class FakeApplication:
        def __init__(self) -> None:
            self.initializationFinished = FakeSignal()
            self.started = False
            self.machine_manager_calls = 0
            self.machine_manager = FakeMachineManager()
            self.preferences: dict[str, str] = {}

        def getPreferences(self) -> object:
            preferences = self.preferences

            class FakePreferences:
                @staticmethod
                def getValue(key: str) -> str:
                    return preferences.get(key, "")

                @staticmethod
                def setValue(key: str, value: str) -> None:
                    preferences[key] = value

            return FakePreferences()

        def getMachineManager(self) -> FakeMachineManager:
            self.machine_manager_calls += 1
            return self.machine_manager

        def getGlobalContainerStack(self) -> None:
            return None

    qt_module = ModuleType("PyQt6.QtCore")
    qt_module.QTimer = FakeTimer  # type: ignore[attr-defined]
    extension_module = ModuleType("UM.Extension")
    extension_module.Extension = FakeExtension  # type: ignore[attr-defined]
    logger_module = ModuleType("UM.Logger")
    logger_module.Logger = FakeLogger  # type: ignore[attr-defined]
    model_module = ModuleType("cura.Machines.Models.BaseMaterialsModel")
    model_module.BaseMaterialsModel = FakeBaseMaterialsModel  # type: ignore[attr-defined]
    for module_name, module in {
        "PyQt6": ModuleType("PyQt6"),
        "PyQt6.QtCore": qt_module,
        "UM": ModuleType("UM"),
        "UM.Extension": extension_module,
        "UM.Logger": logger_module,
        "cura": ModuleType("cura"),
        "cura.Machines": ModuleType("cura.Machines"),
        "cura.Machines.Models": ModuleType("cura.Machines.Models"),
        "cura.Machines.Models.BaseMaterialsModel": model_module,
    }.items():
        monkeypatch.setitem(sys.modules, module_name, module)

    plugin_file = tmp_path / "FilamentManagerVisibility.py"
    plugin_file.write_bytes(plugin)
    specification = importlib.util.spec_from_file_location(
        "filament_manager_visibility_test",
        plugin_file,
    )
    assert specification is not None
    assert specification.loader is not None
    plugin_module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(plugin_module)
    application = FakeApplication()
    plugin_module.FilamentManagerVisibility(application)

    assert application.machine_manager_calls == 0
    application.initializationFinished.emit()
    assert application.machine_manager_calls == 1
    assert application.preferences["material_settings/visible_settings"] == ";".join(
        sorted(_payload()["managed_material_setting_keys"])  # type: ignore[arg-type]
    )


def test_apply_is_idempotent_and_rollback_restores_original(tmp_path: Path, monkeypatch: object) -> None:
    version = _cura_fixture(tmp_path, monkeypatch)
    original = (version / "definition_changes" / "flsun-v400_settings.inst.cfg").read_bytes()
    installation = discover_installations()[0]
    rendered = render_deployment(installation, _payload())
    (version / "materials").mkdir()
    unmanaged_material = version / "materials" / "legacy.xml.fdm_material"
    unmanaged_material.write_text("legacy", encoding="utf-8")
    deployment_id = "9d120f84-24cc-4074-836d-95e82c9459f8"
    first = apply_rendered(installation, deployment_id, "a" * 64, rendered)
    assert first["status"] == "installed"
    manifest = json.loads((version / ".filament-manager" / "manifest.json").read_text())
    assert manifest["library_checksum"] == "a" * 64
    assert manifest["renderer_revision"] == 4
    assert not unmanaged_material.exists()
    second = apply_rendered(installation, deployment_id, "a" * 64, rendered)
    assert second["status"] == "already_current"

    # An upgraded renderer must replace older managed plugin output even when
    # canonical material settings—and therefore the server checksum—did not change.
    manifest.pop("renderer_revision")
    (version / ".filament-manager" / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    assert managed_library_checksum(version) is None
    upgraded = apply_rendered(
        installation,
        "49c3e100-71ae-457d-9329-fcba6e8374a4",
        "a" * 64,
        rendered,
    )
    assert upgraded["status"] == "installed"
    upgraded_manifest = json.loads((version / ".filament-manager" / "manifest.json").read_text())
    assert upgraded_manifest["renderer_revision"] == 4

    assert rollback(deployment_id) == ["Cura 5.10"]
    assert (version / "definition_changes" / "flsun-v400_settings.inst.cfg").read_bytes() == original
    assert unmanaged_material.read_text(encoding="utf-8") == "legacy"
    assert not (version / ".filament-manager" / "manifest.json").exists()


def test_apply_sanitizes_repairs_and_quarantines_user_quality_profiles(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    """Managed keys leave custom profiles while valid quality settings survive."""

    version = _cura_fixture(tmp_path, monkeypatch)
    quality_changes = version / "quality_changes"
    quality_changes.mkdir()
    valid_profile = quality_changes / "flsun_v400_Custom.inst.cfg"
    valid_profile.write_text(
        """[general]
version = 4
name = Custom
definition = flsun_v400

[metadata]
type = quality_changes
quality_type = normal
setting_version = 27

[values]
speed_print = 95
layer_height = 0.16
""",
        encoding="utf-8",
    )
    duplicate_profile = quality_changes / "flsun_v400_Duplicate.inst.cfg"
    duplicate_profile.write_text(
        """[general]
version = 4
name = Duplicate
definition = flsun_v400

[metadata]
type = quality_changes
quality_type = normal

[values]
material_flow = 99
[values]
wall_line_count = 3
""",
        encoding="utf-8",
    )
    corrupt_profile = quality_changes / "flsun_v400_Corrupt.inst.cfg"
    corrupt_profile.write_text("[metadata]\ntype = quality_changes\n", encoding="utf-8")

    installation = discover_installations()[0]
    rendered = render_deployment(installation, _payload())
    result = apply_rendered(
        installation,
        "07f33352-0fab-43d2-a65d-cfdafe9dfca6",
        "a" * 64,
        rendered,
    )

    valid_text = valid_profile.read_text(encoding="utf-8")
    duplicate_text = duplicate_profile.read_text(encoding="utf-8")
    assert "speed_print" not in valid_text
    assert "layer_height = 0.16" in valid_text
    assert "material_flow" not in duplicate_text
    assert "wall_line_count = 3" in duplicate_text
    assert duplicate_text.count("[values]") == 1
    assert not corrupt_profile.exists()
    assert result["quality_profiles_sanitized"] == 2
    assert result["quality_profiles_repaired"] == 1
    assert result["quality_profile_settings_removed"] == 2
    assert result["quality_profiles_quarantined"] == 1
    assert len(result["quarantine_ids"]) == 1
    assert managed_library_checksum(version) == "a" * 64

    valid_profile.write_text(valid_text.replace("[values]", "[values]\nspeed_print = 120"))
    assert managed_library_checksum(version) is None


def test_reports_managed_material_edits_by_guid_without_treating_them_as_new(
    tmp_path: Path, monkeypatch: object
) -> None:
    """Only prefixed known-GUID material files enter the managed edit channel."""

    version = _cura_fixture(tmp_path, monkeypatch)
    installation = discover_installations()[0]
    rendered = render_deployment(installation, _payload())
    material_path = next(path for path in rendered.files if path.parts[0] == "materials")
    target = version / material_path
    target.parent.mkdir(parents=True)
    target.write_bytes(rendered.files[material_path].replace(b">220<", b">225<"))

    assert discover_materials([installation]) == []
    managed = discover_managed_materials([installation])
    assert len(managed) == 1
    report = managed[0].report()
    assert report["material_guid"] == "00000000-0000-4000-8000-000000000001"
    assert report["content_checksum"]
    assert report["settings"]["material_print_temperature"] == "225"


def test_discovers_existing_material_settings_without_reporting_paths(
    tmp_path: Path, monkeypatch: object
) -> None:
    """Approved Cura and Klipper plugin values are available for explicit import."""

    version = _cura_fixture(tmp_path, monkeypatch)
    (version / "materials").mkdir()
    (version / "materials" / "petg.xml.fdm_material").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<fdmmaterial xmlns="http://www.ultimaker.com/material"
  xmlns:cura="http://www.ultimaker.com/cura" version="1.3">
  <metadata><name><brand>Polymaker</brand><material>PETG</material><color>Black</color><label>PolyLite</label></name></metadata>
  <settings>
    <setting key="print temperature">225</setting>
    <cura:setting key="material_flow">98.5</cura:setting>
    <cura:setting key="klipper_pressure_advance_factor">0.035</cura:setting>
    <cura:setting key="machine_start_gcode">unsafe and unsupported</cura:setting>
  </settings>
</fdmmaterial>
""",
        encoding="utf-8",
    )

    materials = discover_materials(discover_installations())

    assert len(materials) == 1
    report = materials[0].report()
    assert report["name"] == "Polymaker PETG · PolyLite"
    assert report["settings"] == {
        "default_material_print_temperature": "225",
        "material_flow": "98.5",
        "klipper_pressure_advance_factor": "0.035",
    }
    assert "path" not in report


def test_discovers_saved_print_profile_layers_with_only_tracked_literal_settings(
    tmp_path: Path, monkeypatch: object
) -> None:
    """Global and first-extruder layers merge without evaluating Cura expressions."""

    version = _cura_fixture(tmp_path, monkeypatch)
    quality_changes = version / "quality_changes"
    quality_changes.mkdir()
    (quality_changes / "flsun_v400_Normal PLA.inst.cfg").write_text(
        """[general]
version = 4
name = Normal PLA
definition = flsun_v400

[metadata]
type = quality_changes
quality_type = normal
setting_version = 27

[values]
speed_print = 80
material_print_temperature = 200
machine_start_gcode = G28
""",
        encoding="utf-8",
    )
    (quality_changes / "flsun_v400_extruder_0_#2_Normal PLA.inst.cfg").write_text(
        """[general]
version = 4
name = Normal PLA
definition = flsun_v400

[metadata]
type = quality_changes
quality_type = normal
setting_version = 27
position = 0

[values]
speed_print = 95
material_bed_temperature = 55
retraction_amount = =machine_nozzle_size * 2
""",
        encoding="utf-8",
    )
    external_profile = tmp_path / "external-profile.cfg"
    external_profile.write_text(
        """[general]
name = Secret Profile

[metadata]
type = quality_changes

[values]
speed_print = 999
""",
        encoding="utf-8",
    )
    (quality_changes / "flsun_v400_Secret Profile.inst.cfg").symlink_to(external_profile)

    installations = discover_installations()
    profiles = discover_print_profiles(installations)

    assert len(profiles) == 1
    report = profiles[0].report()
    assert report["source_kind"] == "print_profile"
    assert report["name"] == "Normal PLA"
    assert report["machine_name"] == "FLSUN V400"
    assert report["quality_type"] == "normal"
    assert report["settings"] == {
        "speed_print": "95",
        "material_print_temperature": "200",
        "material_bed_temperature": "55",
    }
    assert report["omitted_setting_count"] == 1
    assert "path" not in report

    heartbeat = heartbeat_payload(installations)
    assert heartbeat["capabilities"]["cura_print_profile_import"] is True
    assert heartbeat["capabilities"]["unmanaged_print_profile_count"] == 1
    assert heartbeat["capabilities"]["unmanaged_import_source_count"] == 1
    assert heartbeat["cura_materials"][0]["source_kind"] == "print_profile"


def test_reports_saved_profile_with_only_inherited_expressions_for_takeover(
    tmp_path: Path, monkeypatch: object
) -> None:
    """A named Cura profile remains selectable even when it has no literal override."""

    version = _cura_fixture(tmp_path, monkeypatch)
    quality_changes = version / "quality_changes"
    quality_changes.mkdir()
    (quality_changes / "flsun_v400_Inherited PLA.inst.cfg").write_text(
        """[general]
version = 4
name = Inherited PLA
definition = flsun_v400

[metadata]
type = quality_changes
quality_type = normal
setting_version = 27

[values]
speed_print = =machine_max_feedrate_x
retraction_speed = =machine_nozzle_size * 100
""",
        encoding="utf-8",
    )

    installations = discover_installations()
    profiles = discover_print_profiles(installations)
    heartbeat = heartbeat_payload(installations)

    assert len(profiles) == 1
    assert profiles[0].name == "Inherited PLA"
    assert profiles[0].settings == {}
    assert profiles[0].omitted_setting_count == 2
    assert heartbeat["capabilities"]["unmanaged_import_source_count"] == 1
    assert heartbeat["cura_materials"][0]["name"] == "Inherited PLA"


def test_rollback_rejects_path_like_deployment_identity() -> None:
    with pytest.raises(RuntimeError, match="must be a UUID"):
        rollback("../../outside")
