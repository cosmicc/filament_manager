"""Restrictive cross-platform agent configuration persistence."""

import json
import os
import tempfile
from pathlib import Path

from platformdirs import user_config_path, user_data_path

from .models import AgentConfig

APP_NAME = "Filament Manager Agent"


def config_path() -> Path:
    """Return the per-user configuration path, allowing a test/operator override."""

    override = os.environ.get("FILAMENT_MANAGER_AGENT_CONFIG")
    return Path(override).expanduser() if override else user_config_path(APP_NAME) / "config.json"


def data_path() -> Path:
    """Return the private per-user state directory."""

    override = os.environ.get("FILAMENT_MANAGER_AGENT_DATA")
    return Path(override).expanduser() if override else user_data_path(APP_NAME)


def load_config() -> AgentConfig:
    """Load and validate the paired agent configuration."""

    path = config_path()
    if not path.is_file():
        raise RuntimeError("This workstation is not paired. Run 'filament-manager-agent pair' first.")
    return AgentConfig.model_validate_json(path.read_text(encoding="utf-8"))


def save_config(config: AgentConfig) -> None:
    """Atomically persist the credential with owner-only POSIX permissions."""

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            serialized = config.model_dump(mode="json", exclude={"agent_token"})
            # SecretStr masks ordinary serialization. This restrictive file is the credential store.
            serialized["agent_token"] = config.agent_token.get_secret_value()
            json.dump(serialized, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            temporary.chmod(0o600)
        os.replace(temporary, path)
        if os.name == "posix":
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
