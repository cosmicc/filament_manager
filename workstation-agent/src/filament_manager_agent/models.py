"""Validated local configuration and Cura discovery types."""

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, SecretStr, field_validator


class AgentConfig(BaseModel):
    """Persisted scoped credential and polling configuration."""

    server_url: HttpUrl
    agent_id: str
    agent_code: str
    agent_token: SecretStr
    display_name: str
    poll_interval_seconds: int = Field(default=15, ge=5, le=300)

    @field_validator("server_url")
    @classmethod
    def require_secure_server(cls, value: HttpUrl) -> HttpUrl:
        """Permit plaintext only for loopback development."""

        if value.scheme != "https" and value.host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("workstation agent server URL must use HTTPS")
        return value


class CuraMachine(BaseModel):
    """A local Cura machine instance used for deterministic target matching."""

    machine_id: str
    display_name: str
    definition_id: str | None = None
    quality_definition_id: str | None = None
    quality_type: str | None = None
    variant: str | None = None
    nozzle_diameter_mm: str | None = None
    source_path: Path = Field(exclude=True)

    def report(self) -> dict[str, object]:
        """Return server-safe metadata without a workstation path."""

        return self.model_dump(mode="json", exclude={"source_path"})


class CuraInstallation(BaseModel):
    """One writable Cura user data directory."""

    installation_id: str
    version: str
    channel: str
    data_path: Path = Field(exclude=True)
    setting_version: int | None = None
    machines: list[CuraMachine] = Field(default_factory=list)

    def report(self) -> dict[str, object]:
        """Return sanitized discovery data for the management server."""

        return {
            "installation_id": self.installation_id,
            "version": self.version,
            "channel": self.channel,
            "path_hint": f"{self.channel} user data / {self.version}",
            "setting_version": self.setting_version,
            "machines": [machine.report() for machine in self.machines],
        }


class CuraMaterial(BaseModel):
    """Sanitized existing Cura source offered for explicit canonical import."""

    source_id: str
    installation_id: str
    name: str
    brand: str
    material_type: str
    color_name: str
    settings: dict[str, str | bool]
    source_kind: Literal["material", "print_profile"] = "material"
    machine_name: str | None = None
    quality_type: str | None = None
    omitted_setting_count: int = Field(default=0, ge=0)
    material_guid: UUID | None = None
    content_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def report(self) -> dict[str, object]:
        """Return bounded semantic data without exposing the local source path."""

        return self.model_dump(mode="json")


class DeploymentClaim(BaseModel):
    """A leased immutable profile snapshot from the server."""

    deployment_id: UUID
    profile_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, object]
    lease_expires_at: str
