"""Validated application configuration with Docker-secret support."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    """Canonical PostgreSQL pool and secret location."""

    url_file: Path | None = None
    url: SecretStr | None = None
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=100)
    statement_timeout_ms: int = Field(default=30_000, ge=1_000)

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
    full_reconcile_interval_minutes: int = Field(default=30, ge=1)

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
    nozzle_diameter_mm: float = Field(gt=0)


class MoonrakerConfig(BaseModel):
    """Configured printers."""

    printers: list[PrinterConfig] = Field(min_length=1)


class GoogleConfig(BaseModel):
    """Read-only Google Sheet publication settings."""

    enabled: bool = False
    spreadsheet_id: str | None = None
    service_account_file: Path | None = None
    publish_interval_seconds: int = Field(default=30, ge=10)
    write_batch_size: int = Field(default=200, ge=1, le=500)
    unexpected_edit_policy: Literal["warn_and_overwrite", "pause_publication"] = "warn_and_overwrite"

    @model_validator(mode="after")
    def require_google_fields_when_enabled(self) -> "GoogleConfig":
        """Reject an enabled publisher without its required identifiers."""

        if self.enabled and (not self.spreadsheet_id or self.service_account_file is None):
            raise ValueError("enabled Google publication requires spreadsheet_id and service_account_file")
        return self


class SyncConfig(BaseModel):
    """Outbox, reconciliation, and inventory thresholds."""

    max_retry_attempts: int = Field(default=12, ge=1)
    outbox_workers: int = Field(default=2, ge=1, le=32)
    low_spool_threshold_percent: float = Field(default=25, ge=0, le=100)
    measurement_increase_tolerance_percent: float = Field(default=5, ge=0, le=100)
    measurement_increase_tolerance_g: float = Field(default=25, ge=0)


class PlateConfig(BaseModel):
    """Physical plate selection guardrails."""

    allowed_codes: list[Literal["P1", "P2", "P3", "P4", "P5"]]
    selection_policy: Literal["off", "warn", "require"] = "require"
    verify_mesh_loaded: bool = True

    @field_validator("allowed_codes")
    @classmethod
    def preserve_exact_plate_catalog(cls, value: list[str]) -> list[str]:
        """Require the exact supplied plate set without duplicates or omissions."""

        if value != ["P1", "P2", "P3", "P4", "P5"]:
            raise ValueError("allowed_codes must preserve P1 through P5 in order")
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
    """Load settings from the configured YAML file and validate all contracts."""

    if config_path is None:
        import os

        config_path = os.environ.get("FILAMENT_MANAGER_CONFIG", "config/config.local.yaml")
    path = Path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")
    return Settings(**raw)
