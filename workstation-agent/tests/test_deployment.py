"""Transactional Cura rendering and installation tests."""

import json
from pathlib import Path

import pytest

from filament_manager_agent.apply import apply_rendered, rollback
from filament_manager_agent.discovery import discover_installations
from filament_manager_agent.render import MANAGED_START, render_deployment


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
    return {
        "schema_version": 1,
        "profile": {
            "id": "84e0fe98-5994-4c14-aafb-8bb8220b0b9c",
            "version": 2,
            "checksum": "a" * 64,
            "pressure_advance": "0.035",
            "settings": {
                "material_print_temperature": "220",
                "material_bed_temperature": "70",
                "material_flow": "98.5",
                "speed_print": "180",
                "cool_fan_enabled": True,
                "cool_fan_speed": "60",
                "support_angle": "55",
            },
        },
        "material": {
            "product_id": "d1e1d7ce-f0bc-46f5-86b2-d2c74f272f00",
            "brand": "Polymaker",
            "material_type": "PETG",
            "product_name": "PolyLite PETG",
            "color_name": "Black",
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
        "preferred_build_plate": {"code": "P1", "name": "Textured PEI", "surface_type": "PEI"},
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
    assert any(path.startswith("materials/") for path in paths)
    assert sum(path.startswith("quality_changes/") for path in paths) == 2
    pressure_file = next(
        content for path, content in rendered.files.items() if path.parts[0] == "definition_changes"
    )
    assert MANAGED_START.encode() in pressure_file
    assert b"SET_PRESSURE_ADVANCE ADVANCE=0.035" in pressure_file


def test_apply_is_idempotent_and_rollback_restores_original(tmp_path: Path, monkeypatch: object) -> None:
    version = _cura_fixture(tmp_path, monkeypatch)
    original = (version / "definition_changes" / "flsun-v400_settings.inst.cfg").read_bytes()
    installation = discover_installations()[0]
    rendered = render_deployment(installation, _payload())
    deployment_id = "9d120f84-24cc-4074-836d-95e82c9459f8"
    first = apply_rendered(installation, deployment_id, "a" * 64, rendered)
    assert first["status"] == "installed"
    manifest = json.loads((version / ".filament-manager" / "manifest.json").read_text())
    assert manifest["profile_checksum"] == "a" * 64
    second = apply_rendered(installation, deployment_id, "a" * 64, rendered)
    assert second["status"] == "already_current"
    assert rollback(deployment_id) == ["Cura 5.10"]
    assert (version / "definition_changes" / "flsun-v400_settings.inst.cfg").read_bytes() == original
    assert not (version / ".filament-manager" / "manifest.json").exists()


def test_rollback_rejects_path_like_deployment_identity() -> None:
    with pytest.raises(RuntimeError, match="must be a UUID"):
        rollback("../../outside")
