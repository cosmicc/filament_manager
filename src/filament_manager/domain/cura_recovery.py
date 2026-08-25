"""Validation and canonical hashing for sanitized Cura recovery snapshots."""

import configparser
import hashlib
import io
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

RECOVERY_SCHEMA_VERSION = 1
RECOVERY_HISTORY_LIMIT = 10
RECOVERY_FILE_LIMIT = 500
RECOVERY_FILE_MAX_BYTES = 512 * 1024
RECOVERY_TOTAL_MAX_BYTES = 2 * 1024 * 1024
RECOVERY_PLUGIN_LIMIT = 200

RECOVERY_DATA_DIRECTORIES = frozenset(
    {
        "definition_changes",
        "definitions",
        "extruders",
        "intent",
        "machine_instances",
        "quality",
        "quality_changes",
        "setting_visibility",
        "user",
        "variants",
    }
)
RECOVERY_DATA_SUFFIXES = (".cfg", ".def.json")
SAFE_CURA_PREFERENCE_KEYS: Mapping[str, frozenset[str]] = {
    "general": frozenset(
        {
            "accepted_user_agreement",
            "last_run_version",
            "theme",
            "use_tray_icon",
            "version",
            "visible_settings",
            "window_state",
            "window_top",
        }
    ),
    "view": frozenset({"center_on_select", "settings_list_height", "settings_visible", "zoom_to_mouse"}),
    "cura": frozenset(
        {
            "active_machine",
            "active_mode",
            "active_setting_visibility_preset",
            "categories_expanded",
            "choice_on_open_project",
            "currency",
            "custom_visible_settings",
            "expanded_brands",
            "jobname_prefix",
            "select_models_on_load",
            "single_instance",
        }
    ),
    "info": frozenset({"send_engine_crash", "send_slice_info"}),
    "metadata": frozenset({"setting_version"}),
    "mesh": frozenset({"scale_to_fit"}),
    "physics": frozenset({"automatic_push_free"}),
}
SAFE_OFFLINE_PLUGIN_SECTIONS = frozenset(
    {
        "calibrationshapesreborn",
        "material_settings",
        "measuretool",
        "orientationplugin",
        "settings_guide",
        "start_optimiser",
    }
)
SAFE_MOONRAKER_INSTANCE_KEYS = frozenset(
    {
        "retry_interval",
        "output_format",
        "upload_dialog",
        "upload_start_print_job",
        "upload_remember_state",
        "upload_autohide_messagebox",
        "trans_input",
        "trans_output",
        "trans_remove",
        "camera_image_rotation",
        "camera_image_mirror",
        "power_device",
    }
)
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "address",
        "api_key",
        "auth",
        "certificate",
        "credential",
        "directory",
        "filename",
        "folder",
        "host",
        "hostname",
        "password",
        "path",
        "private_key",
        "proxy",
        "secret",
        "token",
        "uri",
        "url",
        "website",
    }
)
_NETWORK_OR_PATH_VALUE = re.compile(
    r"(?:https?|wss?|file)://|(?:^|[\s='\"])(?:[A-Za-z]:[\\/]|\\\\|/[^/\s]|~/)",
    re.IGNORECASE,
)
_SAFE_PLUGIN_ID = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9_.+~-]{1,64}$")
_SAFE_MACHINE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")


class _CaseSensitiveConfigParser(configparser.ConfigParser):
    """Preserve Cura's setting-key case while disabling interpolation."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def recovery_path_is_allowed(scope: str, relative_path: str) -> bool:
    """Return whether a server-supplied recovery target is in the fixed allowlist."""

    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or len(path.parts) == 0:
        return False
    if scope == "config":
        return path.parts == ("cura.cfg",)
    return (
        scope == "data"
        and len(path.parts) == 2
        and path.parts[0] in RECOVERY_DATA_DIRECTORIES
        and path.name.endswith(RECOVERY_DATA_SUFFIXES)
    )


def key_is_sensitive(key: str) -> bool:
    """Recognize credential, network, and local-path fields conservatively."""

    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    compact = normalized.replace("_", "")
    if normalized in _SENSITIVE_KEY_PARTS:
        return True
    if any(
        marker in compact
        for marker in (
            "apikey",
            "authdata",
            "authtoken",
            "bearertoken",
            "clientsecret",
            "credential",
            "password",
            "privatekey",
            "sessionid",
            "sessiontoken",
        )
    ):
        return True
    return any(
        normalized.endswith(f"_{part}") or normalized.startswith(f"{part}_") for part in _SENSITIVE_KEY_PARTS
    )


def value_is_sensitive(value: str) -> bool:
    """Reject explicit network endpoints and workstation-local absolute paths."""

    return bool(_NETWORK_OR_PATH_VALUE.search(value))


def _parse_ini(
    content: str,
    *,
    allow_no_value: bool = False,
) -> configparser.ConfigParser:
    """Parse one Cura INI document without evaluating interpolation tokens.

    Cura setting-visibility presets are intentionally key-only INI-like files.
    Every other recovery document remains strict about requiring values.
    """

    parser = _CaseSensitiveConfigParser(
        interpolation=None,
        strict=False,
        allow_no_value=allow_no_value,
    )
    try:
        parser.read_string(content)
    except (configparser.Error, UnicodeError) as error:
        raise ValueError("Recovery configuration is not valid bounded INI data") from error
    return parser


def _validate_json_value(value: object) -> None:
    """Reject secret-like keys and endpoint/path strings at any JSON depth."""

    if isinstance(value, dict):
        for key, item in value.items():
            if key_is_sensitive(str(key)):
                raise ValueError("Recovery JSON contains a credential, endpoint, or local path field")
            _validate_json_value(item)
    elif isinstance(value, list):
        for item in value:
            _validate_json_value(item)
    elif isinstance(value, str) and value_is_sensitive(value):
        raise ValueError("Recovery JSON contains a network endpoint or local path")


def _validate_moonraker_instances(value: str) -> None:
    """Require a behavior-only Cura2Moonraker instance map."""

    try:
        instances = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("Recovery Moonraker preferences are invalid") from error
    if not isinstance(instances, dict) or len(instances) > 100:
        raise ValueError("Recovery Moonraker preferences are invalid")
    for machine_id, settings in instances.items():
        if (
            not isinstance(machine_id, str)
            or _SAFE_MACHINE_ID.fullmatch(machine_id) is None
            or not isinstance(settings, dict)
        ):
            raise ValueError("Recovery Moonraker preferences are invalid")
        for key, item in settings.items():
            if key not in SAFE_MOONRAKER_INSTANCE_KEYS or not (
                isinstance(item, bool | int | float)
                or (isinstance(item, str) and len(item) <= 160 and not value_is_sensitive(item))
            ):
                raise ValueError("Recovery Moonraker preferences contain an unsupported setting")


def validate_recovery_file(scope: str, relative_path: str, content: str) -> int:
    """Validate one path-free, secret-free text file and return its byte count."""

    if not recovery_path_is_allowed(scope, relative_path):
        raise ValueError("Recovery snapshot contains an unsupported target")
    if "\x00" in content:
        raise ValueError("Recovery snapshot contains invalid control data")
    size = len(content.encode("utf-8"))
    if size > RECOVERY_FILE_MAX_BYTES:
        raise ValueError("Recovery snapshot contains an oversized file")
    if relative_path.endswith(".json"):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("Recovery snapshot contains invalid JSON configuration") from error
        if not isinstance(parsed, dict):
            raise ValueError("Recovery JSON configuration must contain an object")
        _validate_json_value(parsed)
        return size

    path = PurePosixPath(relative_path)
    parser = _parse_ini(
        content,
        allow_no_value=scope == "data" and path.parts[0] == "setting_visibility",
    )
    for section in parser.sections():
        normalized_section = section.casefold()
        for key, value in parser.items(section, raw=True):
            if scope == "config":
                if normalized_section == "moonraker":
                    if key.casefold() != "instances":
                        raise ValueError("Recovery Moonraker preferences contain an unsupported setting")
                    _validate_moonraker_instances(value)
                    continue
                allowed_keys = SAFE_CURA_PREFERENCE_KEYS.get(normalized_section)
                if allowed_keys is None and normalized_section not in SAFE_OFFLINE_PLUGIN_SECTIONS:
                    raise ValueError("Recovery preferences contain an unsupported section")
                if allowed_keys is not None and key.casefold() not in allowed_keys:
                    raise ValueError("Recovery preferences contain an unsupported setting")
            if key_is_sensitive(key) or (value is not None and value_is_sensitive(value)):
                raise ValueError("Recovery snapshot contains a credential, endpoint, or local path")
    return size


def validate_recovery_payload(payload: Mapping[str, Any]) -> tuple[int, int]:
    """Validate complete snapshot bounds and return file count and total bytes."""

    if payload.get("schema_version") != RECOVERY_SCHEMA_VERSION:
        raise ValueError("Unsupported Cura recovery snapshot version")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("Cura recovery snapshot contains no restorable settings")
    if len(raw_files) > RECOVERY_FILE_LIMIT:
        raise ValueError("Cura recovery snapshot contains too many files")
    paths: set[tuple[str, str]] = set()
    total_bytes = 0
    for item in raw_files:
        if not isinstance(item, dict):
            raise ValueError("Cura recovery snapshot contains an invalid file record")
        scope = item.get("scope")
        relative_path = item.get("relative_path")
        content = item.get("content")
        if not isinstance(scope, str) or not isinstance(relative_path, str) or not isinstance(content, str):
            raise ValueError("Cura recovery snapshot file fields must be text")
        identity = (scope, relative_path)
        if identity in paths:
            raise ValueError("Cura recovery snapshot repeats a target")
        paths.add(identity)
        total_bytes += validate_recovery_file(scope, relative_path, content)
    if total_bytes > RECOVERY_TOTAL_MAX_BYTES:
        raise ValueError("Cura recovery snapshot exceeds the total size limit")
    raw_plugins = payload.get("plugins", [])
    if not isinstance(raw_plugins, list) or len(raw_plugins) > RECOVERY_PLUGIN_LIMIT:
        raise ValueError("Cura recovery snapshot contains an invalid plugin inventory")
    plugin_ids: set[str] = set()
    for plugin in raw_plugins:
        if not isinstance(plugin, dict):
            raise ValueError("Cura recovery plugin inventory is invalid")
        plugin_id = plugin.get("package_id")
        display_name = plugin.get("display_name")
        version = plugin.get("version")
        enabled = plugin.get("enabled")
        if (
            not isinstance(plugin_id, str)
            or not _SAFE_PLUGIN_ID.fullmatch(plugin_id)
            or not isinstance(display_name, str)
            or not 1 <= len(display_name) <= 160
            or "\n" in display_name
            or "\r" in display_name
            or value_is_sensitive(display_name)
            or not isinstance(version, str)
            or not _SAFE_VERSION.fullmatch(version)
            or not isinstance(enabled, bool)
            or plugin_id in plugin_ids
        ):
            raise ValueError("Cura recovery plugin inventory is invalid")
        plugin_ids.add(plugin_id)
    return len(raw_files), total_bytes


def recovery_checksum(payload: Mapping[str, Any]) -> str:
    """Return the deterministic checksum for one validated semantic snapshot."""

    validate_recovery_payload(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def suspected_reset(
    *,
    previous_machine_count: int,
    previous_file_count: int,
    previous_quality_profile_count: int,
    machine_count: int,
    file_count: int,
    quality_profile_count: int,
) -> bool:
    """Identify destructive configuration loss without treating ordinary edits as resets."""

    if machine_count < previous_machine_count:
        return True
    if previous_file_count >= 6 and file_count <= previous_file_count * 0.6:
        return True
    return (
        previous_quality_profile_count >= 2 and quality_profile_count <= previous_quality_profile_count * 0.5
    )


def sanitized_ini(
    content: str,
    *,
    preferences: bool,
) -> str:
    """Remove secrets/endpoints/paths and canonicalize a Cura INI file for storage."""

    parser = _parse_ini(content)
    sanitized = _CaseSensitiveConfigParser(interpolation=None, strict=False)
    for section in parser.sections():
        normalized_section = section.casefold()
        allowed_keys = SAFE_CURA_PREFERENCE_KEYS.get(normalized_section)
        if preferences and allowed_keys is None and normalized_section not in SAFE_OFFLINE_PLUGIN_SECTIONS:
            continue
        sanitized.add_section(section)
        for key, value in parser.items(section, raw=True):
            if preferences and allowed_keys is not None and key.casefold() not in allowed_keys:
                continue
            if key_is_sensitive(key) or value_is_sensitive(value):
                continue
            sanitized.set(section, key, value)
    buffer = io.StringIO()
    sanitized.write(buffer, space_around_delimiters=True)
    return buffer.getvalue()


def sorted_snapshot_payload(
    *,
    installation_id: str,
    cura_version: str,
    setting_version: int | None,
    files: Sequence[Mapping[str, str]],
    plugins: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build deterministic payload ordering before hashing or transport."""

    return {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "installation_id": installation_id,
        "cura_version": cura_version,
        "setting_version": setting_version,
        "files": sorted(
            (dict(item) for item in files),
            key=lambda item: (str(item["scope"]), str(item["relative_path"])),
        ),
        "plugins": sorted((dict(item) for item in plugins), key=lambda item: str(item["package_id"])),
    }
