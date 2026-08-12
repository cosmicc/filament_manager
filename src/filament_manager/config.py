"""Validated application configuration with masked credential support."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import yaml
from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseModel):
    """HTTP, logging, timezone, and authentication configuration."""

    base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8080")
    timezone: Literal["America/Detroit"] = "America/Detroit"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    auth_mode: Literal["local"] = "local"
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    cors_origins: list[AnyHttpUrl] = Field(default_factory=list)
    secure_cookies: bool = True
    data_dir: Path = Path("data")
    static_dir: Path = Path("frontend/dist")


class DatabaseConfig(BaseModel):
    """Canonical PostgreSQL pool and credential source."""

    url_file: Path | None = None
    url: SecretStr | None = None
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=100)
    statement_timeout_ms: int = Field(default=30_000, ge=1_000)
    auto_migrate: bool = True
    migration_lock_timeout_seconds: int = Field(default=300, ge=10, le=3600)

    @model_validator(mode="after")
    def require_one_url_source(self) -> "DatabaseConfig":
        """Require exactly one database URL source to avoid ambiguous secrets."""

        if (self.url_file is None) == (self.url is None):
            raise ValueError("database requires exactly one of url_file or url")
        return self

    def resolved_url(self) -> str:
        """Read the URL without including it in model serialization or logs."""

        if self.url is not None:
            value = self.url.get_secret_value().strip()
        else:
            assert self.url_file is not None
            value = self.url_file.read_text(encoding="utf-8").strip()
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("canonical database URL must use PostgreSQL")
        return value


class SpoolmanConfig(BaseModel):
    """Supported Spoolman API connection settings."""

    base_url: AnyHttpUrl
    public_url: AnyHttpUrl | None = None
    request_timeout_seconds: float = Field(default=10, ge=1, le=120)
    full_reconcile_interval_minutes: int = Field(default=1, ge=1)

    @field_validator("base_url", "public_url")
    @classmethod
    def reject_url_credentials(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        """Disallow embedded credentials in outbound service URLs."""

        if value is not None and (value.username or value.password):
            raise ValueError("service URLs must not contain credentials")
        return value


class PrinterConfig(BaseModel):
    """One Moonraker printer connection."""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    base_url: AnyHttpUrl
    websocket_url: str
    api_key_file: Path | None = None
    api_key: SecretStr | None = None
    nozzle_diameter_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def require_one_api_key_source(self) -> "PrinterConfig":
        """Reject ambiguous Moonraker credentials while allowing no API key."""

        if self.api_key_file is not None and self.api_key is not None:
            raise ValueError("Moonraker allows only one of api_key_file or api_key")
        return self

    def resolved_api_key(self) -> str | None:
        """Resolve an optional Moonraker API key without exposing it in logs."""

        if self.api_key is not None:
            return self.api_key.get_secret_value().strip() or None
        if self.api_key_file is not None:
            return self.api_key_file.read_text(encoding="utf-8").strip() or None
        return None


class MoonrakerConfig(BaseModel):
    """Configured printers."""

    printers: list[PrinterConfig] = Field(min_length=1)


class GoogleConfig(BaseModel):
    """Read-only Google Sheet publication settings."""

    enabled: bool = False
    spreadsheet_id: str | None = None
    service_account_file: Path | None = None
    service_account_json: SecretStr | None = None
    publish_interval_seconds: int = Field(default=30, ge=10)
    write_batch_size: int = Field(default=200, ge=1, le=500)
    unexpected_edit_policy: Literal["warn_and_overwrite", "pause_publication"] = "warn_and_overwrite"

    @model_validator(mode="after")
    def require_google_fields_when_enabled(self) -> "GoogleConfig":
        """Reject an enabled publisher without its required identifiers."""

        credential_sources = sum(
            source is not None for source in (self.service_account_file, self.service_account_json)
        )
        if credential_sources > 1:
            raise ValueError(
                "Google publication allows only one of service_account_file or service_account_json"
            )
        if self.enabled and (not self.spreadsheet_id or credential_sources != 1):
            raise ValueError(
                "enabled Google publication requires spreadsheet_id and one service-account source"
            )
        if self.service_account_json is not None:
            try:
                document = json.loads(self.service_account_json.get_secret_value())
            except json.JSONDecodeError as exc:
                raise ValueError("Google service-account JSON must be valid JSON") from exc
            if not isinstance(document, dict):
                raise ValueError("Google service-account JSON must be an object")
        return self

    def resolved_service_account_info(self) -> dict[str, Any] | None:
        """Return inline Google credentials only to the bound API client."""

        if self.service_account_json is None:
            return None
        document = json.loads(self.service_account_json.get_secret_value())
        assert isinstance(document, dict)
        return document


class SyncConfig(BaseModel):
    """Outbox, reconciliation, and inventory thresholds."""

    max_retry_attempts: int = Field(default=12, ge=1)
    outbox_workers: int = Field(default=2, ge=1, le=32)
    outbox_lock_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    low_spool_threshold_percent: float = Field(default=25, ge=0, le=100)
    measurement_increase_tolerance_percent: float = Field(default=5, ge=0, le=100)
    measurement_increase_tolerance_g: float = Field(default=25, ge=0)


class PlateConfig(BaseModel):
    """Initial physical plate seeds and selection guardrails."""

    allowed_codes: list[Literal["P1", "P2", "P3", "P4", "P5"]]
    selection_policy: Literal["off", "warn", "require"] = "require"
    verify_mesh_loaded: bool = True

    @field_validator("allowed_codes")
    @classmethod
    def preserve_exact_plate_catalog(cls, value: list[str]) -> list[str]:
        """Require the exact initial plate set without duplicates or omissions."""

        if value != ["P1", "P2", "P3", "P4", "P5"]:
            raise ValueError("allowed_codes must preserve the initial P1 through P5 order")
        return value


class DeviceConfig(BaseModel):
    """Future hardware acceptance settings."""

    scale_enabled: bool = False
    nfc_enabled: bool = False
    stable_window_seconds: float = Field(default=10, ge=1)
    stable_variance_g: float = Field(default=2, ge=0)
    replay_window_seconds: int = Field(default=300, ge=1)


class SecurityConfig(BaseModel):
    """Local account and session security controls."""

    session_lifetime_hours: int = Field(default=12, ge=1, le=168)
    session_idle_minutes: int = Field(default=60, ge=5, le=1440)
    max_failed_logins: int = Field(default=5, ge=3, le=20)
    lockout_minutes: int = Field(default=15, ge=1, le=1440)


class Settings(BaseSettings):
    """Complete validated runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="FILAMENT_MANAGER_", env_nested_delimiter="__", extra="forbid"
    )

    app: AppConfig
    database: DatabaseConfig
    spoolman: SpoolmanConfig
    moonraker: MoonrakerConfig
    google: GoogleConfig
    sync: SyncConfig
    plates: PlateConfig
    devices: DeviceConfig
    security: SecurityConfig = Field(default_factory=SecurityConfig)


@lru_cache
def get_settings(config_path: str | None = None) -> Settings:
    """Load environment-only Docker settings or an explicit/local YAML file."""

    configured_path = config_path or os.environ.get("FILAMENT_MANAGER_CONFIG")
    if configured_path is not None:
        raw = _load_yaml_config(Path(configured_path))
        _apply_credential_environment(raw)
    elif os.environ.get("FILAMENT_MANAGER_DATABASE_URL"):
        raw = _deployment_environment_config()
    else:
        raw = _load_yaml_config(Path("config/config.local.yaml"))
    return Settings(**raw)


def _load_yaml_config(path: Path) -> dict[str, Any]:
    """Read one YAML configuration document for non-Docker operation."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")
    return raw


def _environment_boolean(name: str, default: bool) -> bool:
    """Read a strict human-friendly boolean environment value."""

    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _environment_csv(name: str, default: list[str] | None = None) -> list[str]:
    """Read a comma-separated environment list without empty entries."""

    value = os.environ.get(name)
    if value is None or not value.strip():
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def _derive_websocket_url(base_url: str) -> str:
    """Derive Moonraker's WebSocket endpoint from its HTTP base URL."""

    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("FILAMENT_MANAGER_MOONRAKER_BASE_URL must be an HTTP(S) URL")
    websocket_scheme = "wss" if parsed.scheme == "https" else "ws"
    websocket_path = f"{parsed.path.rstrip('/')}/websocket"
    return urlunsplit((websocket_scheme, parsed.netloc, websocket_path, "", ""))


def _deployment_environment_config() -> dict[str, Any]:
    """Build the complete one-printer Docker configuration from environment values."""

    app_base_url = os.environ.get("FILAMENT_MANAGER_BASE_URL", "http://localhost:8080")
    app_hostname = urlsplit(app_base_url).hostname
    if app_hostname is None:
        raise ValueError("FILAMENT_MANAGER_BASE_URL must include a hostname")

    moonraker_base_url = os.environ.get("FILAMENT_MANAGER_MOONRAKER_BASE_URL", "http://localhost:7125")
    moonraker_websocket_url = os.environ.get(
        "FILAMENT_MANAGER_MOONRAKER_WEBSOCKET_URL"
    ) or _derive_websocket_url(moonraker_base_url)

    database: dict[str, Any] = {
        "url": os.environ["FILAMENT_MANAGER_DATABASE_URL"],
        "pool_size": os.environ.get("FILAMENT_MANAGER_DATABASE_POOL_SIZE", "10"),
        "max_overflow": os.environ.get("FILAMENT_MANAGER_DATABASE_MAX_OVERFLOW", "10"),
        "statement_timeout_ms": os.environ.get("FILAMENT_MANAGER_DATABASE_STATEMENT_TIMEOUT_MS", "30000"),
        "auto_migrate": _environment_boolean("FILAMENT_MANAGER_DATABASE_AUTO_MIGRATE", True),
        "migration_lock_timeout_seconds": os.environ.get(
            "FILAMENT_MANAGER_DATABASE_MIGRATION_LOCK_TIMEOUT_SECONDS", "300"
        ),
    }
    spoolman: dict[str, Any] = {
        "base_url": os.environ.get("FILAMENT_MANAGER_SPOOLMAN_BASE_URL", "http://spoolman:8000"),
        "request_timeout_seconds": os.environ.get("FILAMENT_MANAGER_SPOOLMAN_REQUEST_TIMEOUT_SECONDS", "10"),
        "full_reconcile_interval_minutes": os.environ.get(
            "FILAMENT_MANAGER_SPOOLMAN_RECONCILE_INTERVAL_MINUTES", "1"
        ),
    }
    if public_url := os.environ.get("FILAMENT_MANAGER_SPOOLMAN_PUBLIC_URL"):
        spoolman["public_url"] = public_url

    printer: dict[str, Any] = {
        "id": os.environ.get("FILAMENT_MANAGER_MOONRAKER_PRINTER_ID", "printer-1"),
        "name": os.environ.get("FILAMENT_MANAGER_MOONRAKER_PRINTER_NAME", "3D Printer"),
        "base_url": moonraker_base_url,
        "websocket_url": moonraker_websocket_url,
        "nozzle_diameter_mm": os.environ.get("FILAMENT_MANAGER_MOONRAKER_NOZZLE_DIAMETER_MM", "0.4"),
    }
    if api_key := os.environ.get("FILAMENT_MANAGER_MOONRAKER_API_KEY"):
        printer["api_key"] = api_key

    google: dict[str, Any] = {
        "enabled": _environment_boolean("FILAMENT_MANAGER_GOOGLE_ENABLED", False),
        "publish_interval_seconds": os.environ.get("FILAMENT_MANAGER_GOOGLE_PUBLISH_INTERVAL_SECONDS", "30"),
        "write_batch_size": os.environ.get("FILAMENT_MANAGER_GOOGLE_WRITE_BATCH_SIZE", "200"),
        "unexpected_edit_policy": os.environ.get(
            "FILAMENT_MANAGER_GOOGLE_UNEXPECTED_EDIT_POLICY", "warn_and_overwrite"
        ),
    }
    if spreadsheet_id := os.environ.get("FILAMENT_MANAGER_GOOGLE_SPREADSHEET_ID"):
        google["spreadsheet_id"] = spreadsheet_id
    if service_account_json := os.environ.get("FILAMENT_MANAGER_GOOGLE_SERVICE_ACCOUNT_JSON"):
        google["service_account_json"] = service_account_json

    return {
        "app": {
            "base_url": app_base_url,
            "timezone": os.environ.get("FILAMENT_MANAGER_TIMEZONE", "America/Detroit"),
            "log_level": os.environ.get("FILAMENT_MANAGER_LOG_LEVEL", "INFO"),
            "auth_mode": "local",
            "allowed_hosts": _environment_csv("FILAMENT_MANAGER_ALLOWED_HOSTS", [app_hostname]),
            "cors_origins": _environment_csv("FILAMENT_MANAGER_CORS_ORIGINS"),
            "secure_cookies": _environment_boolean("FILAMENT_MANAGER_SECURE_COOKIES", True),
            "data_dir": "/data",
            "static_dir": "/app/static",
        },
        "database": database,
        "spoolman": spoolman,
        "moonraker": {"printers": [printer]},
        "google": google,
        "sync": {
            "max_retry_attempts": os.environ.get("FILAMENT_MANAGER_SYNC_MAX_RETRY_ATTEMPTS", "12"),
            "outbox_workers": os.environ.get("FILAMENT_MANAGER_SYNC_OUTBOX_WORKERS", "2"),
            "outbox_lock_timeout_seconds": os.environ.get(
                "FILAMENT_MANAGER_SYNC_OUTBOX_LOCK_TIMEOUT_SECONDS", "300"
            ),
            "low_spool_threshold_percent": os.environ.get(
                "FILAMENT_MANAGER_LOW_SPOOL_THRESHOLD_PERCENT", "25"
            ),
            "measurement_increase_tolerance_percent": os.environ.get(
                "FILAMENT_MANAGER_MEASUREMENT_INCREASE_TOLERANCE_PERCENT", "5"
            ),
            "measurement_increase_tolerance_g": os.environ.get(
                "FILAMENT_MANAGER_MEASUREMENT_INCREASE_TOLERANCE_G", "25"
            ),
        },
        "plates": {
            "allowed_codes": ["P1", "P2", "P3", "P4", "P5"],
            "selection_policy": os.environ.get("FILAMENT_MANAGER_PLATE_SELECTION_POLICY", "require"),
            "verify_mesh_loaded": _environment_boolean("FILAMENT_MANAGER_VERIFY_MESH_LOADED", True),
        },
        "devices": {
            "scale_enabled": _environment_boolean("FILAMENT_MANAGER_SCALE_ENABLED", False),
            "nfc_enabled": _environment_boolean("FILAMENT_MANAGER_NFC_ENABLED", False),
            "stable_window_seconds": os.environ.get("FILAMENT_MANAGER_STABLE_WINDOW_SECONDS", "10"),
            "stable_variance_g": os.environ.get("FILAMENT_MANAGER_STABLE_VARIANCE_G", "2"),
            "replay_window_seconds": os.environ.get("FILAMENT_MANAGER_REPLAY_WINDOW_SECONDS", "300"),
        },
        "security": {
            "session_lifetime_hours": os.environ.get("FILAMENT_MANAGER_SESSION_LIFETIME_HOURS", "12"),
            "session_idle_minutes": os.environ.get("FILAMENT_MANAGER_SESSION_IDLE_MINUTES", "60"),
            "max_failed_logins": os.environ.get("FILAMENT_MANAGER_MAX_FAILED_LOGINS", "5"),
            "lockout_minutes": os.environ.get("FILAMENT_MANAGER_LOCKOUT_MINUTES", "15"),
        },
    }


def _apply_credential_environment(raw: dict[str, Any]) -> None:
    """Overlay explicitly supported container credentials onto YAML configuration.

    Stack environment values intentionally replace file-backed values so a
    deployment cannot accidentally configure two credential sources at once.
    Empty optional integration values are treated as not configured.
    """

    database_url = os.environ.get("FILAMENT_MANAGER_DATABASE_URL")
    if database_url:
        database = raw.setdefault("database", {})
        if not isinstance(database, dict):
            raise ValueError("database configuration must be a mapping")
        database.pop("url_file", None)
        database["url"] = database_url

    moonraker_api_key = os.environ.get("FILAMENT_MANAGER_MOONRAKER_API_KEY")
    if moonraker_api_key:
        moonraker = raw.get("moonraker")
        printers = moonraker.get("printers") if isinstance(moonraker, dict) else None
        if not isinstance(printers, list):
            raise ValueError("moonraker.printers configuration must be a list")
        for printer in printers:
            if not isinstance(printer, dict):
                raise ValueError("each Moonraker printer configuration must be a mapping")
            printer.pop("api_key_file", None)
            printer["api_key"] = moonraker_api_key

    google_service_account_json = os.environ.get("FILAMENT_MANAGER_GOOGLE_SERVICE_ACCOUNT_JSON")
    if google_service_account_json:
        google = raw.setdefault("google", {})
        if not isinstance(google, dict):
            raise ValueError("google configuration must be a mapping")
        google.pop("service_account_file", None)
        google["service_account_json"] = google_service_account_json
