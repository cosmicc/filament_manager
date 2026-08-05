"""Agent configuration and path trust-boundary tests."""

from pathlib import Path

import pytest

from filament_manager_agent.apply import _safe_target
from filament_manager_agent.config import load_config, save_config
from filament_manager_agent.models import AgentConfig


def test_managed_target_cannot_escape_cura_root(tmp_path: Path) -> None:
    root = tmp_path / "5.10"
    root.mkdir()
    with pytest.raises(ValueError, match="escaped"):
        _safe_target(root, Path("..") / "outside.cfg")


def test_managed_target_rejects_existing_symlink(tmp_path: Path) -> None:
    root = tmp_path / "5.10"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "materials").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symbolic link"):
        _safe_target(root, Path("materials") / "profile.xml.fdm_material")


def test_agent_token_round_trips_only_through_private_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "private" / "config.json"
    monkeypatch.setenv("FILAMENT_MANAGER_AGENT_CONFIG", str(path))
    save_config(
        AgentConfig(
            server_url="https://filament-manager.example",
            agent_id="agent-id",
            agent_code="WS-12345678",
            agent_token="fm_agent_test_only_secret",
            display_name="Test Cura",
        )
    )
    assert load_config().agent_token.get_secret_value() == "fm_agent_test_only_secret"
    assert "fm_agent_test_only_secret" in path.read_text(encoding="utf-8")
    assert path.stat().st_mode & 0o777 == 0o600


def test_remote_agent_server_requires_https() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        AgentConfig(
            server_url="http://filament-manager.example",
            agent_id="agent-id",
            agent_code="WS-12345678",
            agent_token="fm_agent_test_only_secret",
            display_name="Test Cura",
        )
