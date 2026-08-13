"""Configuration credential-source and masking tests."""

from pathlib import Path

import pytest
import typer

from filament_manager.cli import _resolve_bootstrap_password
from filament_manager.config import get_settings


def test_docker_configuration_comes_from_environment_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker settings are complete, validated, and masked without mounted YAML."""

    database_url = (
        "postgresql+psycopg://filament_user:database-password@postgres.example/filament_manager"
        "?sslmode=disable"
    )
    moonraker_key = "moonraker-api-key"
    google_document = '{"type":"service_account","client_email":"agent@example.invalid"}'
    monkeypatch.delenv("FILAMENT_MANAGER_CONFIG", raising=False)
    monkeypatch.setenv("FILAMENT_MANAGER_BASE_URL", "https://filament.example")
    monkeypatch.setenv("FILAMENT_MANAGER_ALLOWED_HOSTS", "filament.example,filament.lan")
    monkeypatch.setenv("FILAMENT_MANAGER_CORS_ORIGINS", "https://admin.example")
    monkeypatch.setenv("FILAMENT_MANAGER_SECURE_COOKIES", "true")
    monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", database_url)
    monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_POOL_SIZE", "14")
    monkeypatch.setenv("FILAMENT_MANAGER_SPOOLMAN_BASE_URL", "http://spoolman:8000")
    monkeypatch.setenv("FILAMENT_MANAGER_SPOOLMAN_PUBLIC_URL", "http://spoolman.example:7912")
    monkeypatch.setenv("FILAMENT_MANAGER_MOONRAKER_PRINTER_ID", "voron-24")
    monkeypatch.setenv("FILAMENT_MANAGER_MOONRAKER_PRINTER_NAME", "Voron 2.4")
    monkeypatch.setenv("FILAMENT_MANAGER_MOONRAKER_BASE_URL", "https://voron.example:7125")
    monkeypatch.setenv("FILAMENT_MANAGER_MOONRAKER_API_KEY", moonraker_key)
    monkeypatch.setenv("FILAMENT_MANAGER_MOONRAKER_NOZZLE_DIAMETER_MM", "0.6")
    monkeypatch.setenv("FILAMENT_MANAGER_MOONRAKER_STATE_INTERVAL_SECONDS", "12")
    monkeypatch.setenv("FILAMENT_MANAGER_MOONRAKER_INFO_INTERVAL_SECONDS", "240")
    monkeypatch.setenv("FILAMENT_MANAGER_GOOGLE_ENABLED", "true")
    monkeypatch.setenv("FILAMENT_MANAGER_GOOGLE_SPREADSHEET_ID", "sheet-id")
    monkeypatch.setenv("FILAMENT_MANAGER_GOOGLE_SERVICE_ACCOUNT_JSON", google_document)
    monkeypatch.setenv("FILAMENT_MANAGER_LOW_SPOOL_THRESHOLD_PERCENT", "20")

    get_settings.cache_clear()
    settings = get_settings()

    assert str(settings.app.base_url) == "https://filament.example/"
    assert settings.app.allowed_hosts == ["filament.example", "filament.lan"]
    assert [str(origin) for origin in settings.app.cors_origins] == ["https://admin.example/"]
    assert settings.database.url_file is None
    assert settings.database.resolved_url() == database_url
    assert settings.database.pool_size == 14
    assert settings.database.auto_migrate is True
    assert settings.database.migration_lock_timeout_seconds == 300
    assert str(settings.spoolman.base_url) == "http://spoolman:8000/"
    assert str(settings.spoolman.public_url) == "http://spoolman.example:7912/"
    assert settings.spoolman.full_reconcile_interval_minutes == 1
    assert settings.sync.outbox_lock_timeout_seconds == 300
    assert settings.sync.moonraker_state_interval_seconds == 12
    assert settings.sync.moonraker_info_interval_seconds == 240
    assert settings.moonraker.printers[0].api_key_file is None
    assert settings.moonraker.printers[0].resolved_api_key() == moonraker_key
    assert settings.moonraker.printers[0].id == "voron-24"
    assert settings.moonraker.printers[0].name == "Voron 2.4"
    assert settings.moonraker.printers[0].websocket_url == "wss://voron.example:7125/websocket"
    assert settings.moonraker.printers[0].nozzle_diameter_mm == 0.6
    assert settings.google.enabled is True
    assert settings.google.service_account_file is None
    assert settings.google.resolved_service_account_info() == {
        "type": "service_account",
        "client_email": "agent@example.invalid",
    }
    rendered = repr(settings)
    assert "database-password" not in rendered
    assert moonraker_key not in rendered
    assert "agent@example.invalid" not in rendered
    get_settings.cache_clear()


def test_environment_configuration_rejects_invalid_boolean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mistyped stack booleans fail closed instead of silently changing behavior."""

    monkeypatch.delenv("FILAMENT_MANAGER_CONFIG", raising=False)
    monkeypatch.setenv(
        "FILAMENT_MANAGER_DATABASE_URL",
        "postgresql+psycopg://user:password@postgres.example/database",
    )
    monkeypatch.setenv("FILAMENT_MANAGER_SECURE_COOKIES", "sometimes")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="FILAMENT_MANAGER_SECURE_COOKIES"):
        get_settings()

    get_settings.cache_clear()


def test_bootstrap_password_uses_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one-shot bootstrap can use its scoped stack environment value."""

    monkeypatch.setenv("FILAMENT_MANAGER_BOOTSTRAP_ADMIN_PASSWORD", "temporary-password")

    assert _resolve_bootstrap_password(None) == "temporary-password"


def test_bootstrap_password_rejects_ambiguous_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A file and environment value cannot silently compete."""

    password_file = tmp_path / "password.txt"
    password_file.write_text("file-password\n", encoding="utf-8")
    monkeypatch.setenv("FILAMENT_MANAGER_BOOTSTRAP_ADMIN_PASSWORD", "environment-password")

    with pytest.raises(typer.BadParameter, match="set only one"):
        _resolve_bootstrap_password(password_file)
