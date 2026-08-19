"""Capture and restore bounded secret-free Cura workstation configuration."""

import configparser
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

from .apply import _atomic_write, _deployment_key, _safe_target
from .config import data_path
from .models import CuraInstallation

RECOVERY_SCHEMA_VERSION = 1
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
SAFE_CURA_PREFERENCE_KEYS: dict[str, frozenset[str]] = {
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
_PLUGIN_ID = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_PLUGIN_VERSION = re.compile(r"^[A-Za-z0-9_.+~-]{1,64}$")


class _CaseSensitiveConfigParser(configparser.ConfigParser):
    """Preserve Cura's setting-key case while disabling interpolation."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def _parser() -> configparser.ConfigParser:
    return _CaseSensitiveConfigParser(interpolation=None, strict=False)


def _key_is_sensitive(key: str) -> bool:
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


def _value_is_sensitive(value: str) -> bool:
    return bool(_NETWORK_OR_PATH_VALUE.search(value))


def _sanitize_ini(content: str, *, preferences: bool) -> str:
    source = _parser()
    try:
        source.read_string(content)
    except (configparser.Error, UnicodeError) as error:
        raise RuntimeError("A supported Cura configuration file is invalid.") from error
    sanitized = _parser()
    for section in source.sections():
        normalized_section = section.casefold()
        allowed_keys = SAFE_CURA_PREFERENCE_KEYS.get(normalized_section)
        if preferences and allowed_keys is None and normalized_section not in SAFE_OFFLINE_PLUGIN_SECTIONS:
            continue
        sanitized.add_section(section)
        for key, value in source.items(section, raw=True):
            if preferences and allowed_keys is not None and key.casefold() not in allowed_keys:
                continue
            if _key_is_sensitive(key) or _value_is_sensitive(value):
                continue
            sanitized.set(section, key, value)
    output = io.StringIO()
    sanitized.write(output, space_around_delimiters=True)
    return output.getvalue()


def _sanitize_json_value(value: object) -> object | None:
    if isinstance(value, dict):
        return {
            str(key): sanitized
            for key, item in value.items()
            if not _key_is_sensitive(str(key)) and (sanitized := _sanitize_json_value(item)) is not None
        }
    if isinstance(value, list):
        return [sanitized for item in value if (sanitized := _sanitize_json_value(item)) is not None]
    if isinstance(value, str):
        return None if _value_is_sensitive(value) else value
    if value is None or isinstance(value, bool | int | float):
        return value
    return None


def _sanitize_json(content: str) -> str:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError("A supported Cura JSON configuration file is invalid.") from error
    if not isinstance(parsed, dict):
        raise RuntimeError("A supported Cura JSON configuration file has an invalid root.")
    sanitized = _sanitize_json_value(parsed)
    assert isinstance(sanitized, dict)
    return json.dumps(sanitized, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _read_bounded_text(path: Path) -> str:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > RECOVERY_FILE_MAX_BYTES:
            raise RuntimeError("A supported Cura recovery file is unsafe or oversized.")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RuntimeError("A supported Cura recovery file could not be read safely.") from error


def _plugin_inventory(installation: CuraInstallation) -> list[dict[str, object]]:
    packages_path = installation.data_path / "packages.json"
    config_root = installation.config_path or installation.data_path
    plugins_path = config_root / "plugins.json"
    try:
        packages = json.loads(packages_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    installed = packages.get("installed") if isinstance(packages, dict) else None
    if not isinstance(installed, dict):
        return []
    disabled: set[str] = set()
    try:
        plugin_state = json.loads(plugins_path.read_text(encoding="utf-8"))
        raw_disabled = plugin_state.get("disabled") if isinstance(plugin_state, dict) else None
        if isinstance(raw_disabled, list):
            disabled = {str(item) for item in raw_disabled if isinstance(item, str)}
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    inventory: list[dict[str, object]] = []
    for raw_id, item in sorted(installed.items())[:RECOVERY_PLUGIN_LIMIT]:
        if not isinstance(raw_id, str) or not _PLUGIN_ID.fullmatch(raw_id) or not isinstance(item, dict):
            continue
        package_info = item.get("package_info")
        if not isinstance(package_info, dict):
            continue
        display_name = package_info.get("display_name")
        version = package_info.get("package_version")
        if (
            not isinstance(display_name, str)
            or not 1 <= len(display_name) <= 160
            or "\n" in display_name
            or "\r" in display_name
            or _value_is_sensitive(display_name)
            or not isinstance(version, str)
            or not _PLUGIN_VERSION.fullmatch(version)
        ):
            continue
        inventory.append(
            {
                "package_id": raw_id,
                "display_name": display_name,
                "version": version,
                "enabled": raw_id not in disabled,
            }
        )
    return inventory


def _snapshot_checksum(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def capture_recovery_snapshot(installation: CuraInstallation) -> dict[str, object]:
    """Capture restorable user configuration without paths, credentials, or plugin code."""

    files: list[dict[str, str]] = []
    total_bytes = 0
    for directory_name in sorted(RECOVERY_DATA_DIRECTORIES):
        directory = installation.data_path / directory_name
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError("A supported Cura recovery directory is unsafe.")
        for path in sorted(directory.iterdir()):
            if not path.name.endswith(RECOVERY_DATA_SUFFIXES):
                continue
            content = _read_bounded_text(path)
            sanitized = (
                _sanitize_json(content)
                if path.name.endswith(".json")
                else _sanitize_ini(content, preferences=False)
            )
            encoded_size = len(sanitized.encode("utf-8"))
            total_bytes += encoded_size
            if len(files) >= RECOVERY_FILE_LIMIT or total_bytes > RECOVERY_TOTAL_MAX_BYTES:
                raise RuntimeError("Cura recovery settings exceed the safe capture limit.")
            files.append(
                {
                    "scope": "data",
                    "relative_path": PurePosixPath(directory_name, path.name).as_posix(),
                    "content": sanitized,
                }
            )
    config_root = installation.config_path or installation.data_path
    preferences_path = config_root / "cura.cfg"
    if preferences_path.is_file():
        preferences = _sanitize_ini(_read_bounded_text(preferences_path), preferences=True)
        if preferences.strip():
            total_bytes += len(preferences.encode("utf-8"))
            if len(files) >= RECOVERY_FILE_LIMIT or total_bytes > RECOVERY_TOTAL_MAX_BYTES:
                raise RuntimeError("Cura recovery settings exceed the safe capture limit.")
            files.append({"scope": "config", "relative_path": "cura.cfg", "content": preferences})
    payload: dict[str, object] = {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "installation_id": installation.installation_id,
        "cura_version": installation.version,
        "setting_version": installation.setting_version,
        "files": sorted(files, key=lambda item: (item["scope"], item["relative_path"])),
        "plugins": _plugin_inventory(installation),
    }
    return {"snapshot_checksum": _snapshot_checksum(payload), "payload": payload}


def _recovery_files(payload: dict[str, object]) -> list[dict[str, str]]:
    if payload.get("schema_version") != RECOVERY_SCHEMA_VERSION:
        raise RuntimeError("The Cura recovery snapshot version is unsupported.")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list) or not raw_files or len(raw_files) > RECOVERY_FILE_LIMIT:
        raise RuntimeError("The Cura recovery snapshot file manifest is invalid.")
    files: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    total_bytes = 0
    for item in raw_files:
        if not isinstance(item, dict):
            raise RuntimeError("The Cura recovery snapshot file manifest is invalid.")
        scope = item.get("scope")
        relative_path = item.get("relative_path")
        content = item.get("content")
        if not isinstance(scope, str) or not isinstance(relative_path, str) or not isinstance(content, str):
            raise RuntimeError("The Cura recovery snapshot file manifest is invalid.")
        path = PurePosixPath(relative_path)
        allowed = (scope == "config" and path.parts == ("cura.cfg",)) or (
            scope == "data"
            and len(path.parts) == 2
            and path.parts[0] in RECOVERY_DATA_DIRECTORIES
            and path.name.endswith(RECOVERY_DATA_SUFFIXES)
        )
        identity = (scope, relative_path)
        size = len(content.encode("utf-8"))
        if not allowed or identity in seen or size > RECOVERY_FILE_MAX_BYTES:
            raise RuntimeError("The Cura recovery snapshot contains an unsafe target.")
        if relative_path.endswith(".json"):
            sanitized = _sanitize_json(content)
        else:
            sanitized = _sanitize_ini(content, preferences=scope == "config")
        if sanitized != content:
            raise RuntimeError("The Cura recovery snapshot failed local sanitization.")
        seen.add(identity)
        total_bytes += size
        files.append({"scope": scope, "relative_path": relative_path, "content": content})
    if total_bytes > RECOVERY_TOTAL_MAX_BYTES:
        raise RuntimeError("The Cura recovery snapshot exceeds the safe size limit.")
    return files


def _merge_preferences(current_content: str, saved_content: str) -> bytes:
    current = _parser()
    saved = _parser()
    try:
        current.read_string(current_content)
        saved.read_string(saved_content)
    except (configparser.Error, UnicodeError) as error:
        raise RuntimeError("Cura preferences could not be merged safely.") from error
    for section_name, allowed_keys in SAFE_CURA_PREFERENCE_KEYS.items():
        current_section = next(
            (section for section in current.sections() if section.casefold() == section_name),
            None,
        )
        if current_section is not None:
            for key in list(current[current_section]):
                if key.casefold() in allowed_keys:
                    current.remove_option(current_section, key)
    for section in list(current.sections()):
        if section.casefold() in SAFE_OFFLINE_PLUGIN_SECTIONS:
            current.remove_section(section)
    for section in saved.sections():
        if not current.has_section(section):
            current.add_section(section)
        for key, value in saved.items(section, raw=True):
            current.set(section, key, value)
    output = io.StringIO()
    current.write(output, space_around_delimiters=True)
    return output.getvalue().encode("utf-8")


def _backup_restore_targets(
    installation: CuraInstallation,
    restore_id: str,
    data_targets: set[Path],
    preferences_target: Path | None,
) -> tuple[Path, set[str]]:
    backup_directory = data_path() / "recovery-backups" / restore_id
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / f"{installation.installation_id}.zip"
    existed: set[str] = set()
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(data_targets, key=lambda item: item.as_posix()):
            target = _safe_target(installation.data_path, relative)
            if target.is_file():
                archive_name = PurePosixPath("data", relative.as_posix()).as_posix()
                existed.add(archive_name)
                archive.writestr(archive_name, target.read_bytes())
        if preferences_target is not None and preferences_target.is_file():
            existed.add("config/cura.cfg")
            archive.writestr("config/cura.cfg", preferences_target.read_bytes())
        archive.writestr(
            ".filament-manager-recovery-backup.json",
            json.dumps(
                {
                    "data_targets": sorted(item.as_posix() for item in data_targets),
                    "preferences_targeted": preferences_target is not None,
                    "existed": sorted(existed),
                },
                sort_keys=True,
            ),
        )
    return backup_path, existed


def _restore_failed_recovery(
    installation: CuraInstallation,
    backup_path: Path,
    data_targets: set[Path],
    preferences_target: Path | None,
    existed: set[str],
) -> None:
    with zipfile.ZipFile(backup_path) as archive:
        names = set(archive.namelist())
        for relative in data_targets:
            target = _safe_target(installation.data_path, relative)
            archive_name = PurePosixPath("data", relative.as_posix()).as_posix()
            if archive_name in existed and archive_name in names:
                _atomic_write(target, archive.read(archive_name))
            else:
                target.unlink(missing_ok=True)
        if preferences_target is not None:
            if "config/cura.cfg" in existed and "config/cura.cfg" in names:
                _atomic_write(preferences_target, archive.read("config/cura.cfg"))
            else:
                preferences_target.unlink(missing_ok=True)


def _current_recovery_targets(installation: CuraInstallation) -> set[Path]:
    targets: set[Path] = set()
    for directory_name in RECOVERY_DATA_DIRECTORIES:
        directory = installation.data_path / directory_name
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise RuntimeError("A supported Cura recovery directory is unsafe.")
        for path in directory.iterdir():
            if path.name.endswith(RECOVERY_DATA_SUFFIXES):
                targets.add(Path(directory_name) / path.name)
    return targets


def restore_recovery_snapshot(
    installation: CuraInstallation,
    restore_id: str,
    expected_checksum: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Back up, replace, and roll back one exact-version sanitized Cura recovery point."""

    restore_id = _deployment_key(restore_id)
    if (
        payload.get("installation_id") != installation.installation_id
        or payload.get("cura_version") != installation.version
    ):
        raise RuntimeError("The Cura recovery point does not match this exact installation.")
    if _snapshot_checksum(payload) != expected_checksum:
        raise RuntimeError("The Cura recovery snapshot checksum is invalid.")
    files = _recovery_files(payload)
    desired_data = {
        Path(item["relative_path"]): item["content"].encode("utf-8")
        for item in files
        if item["scope"] == "data"
    }
    saved_preferences = next(
        (item["content"] for item in files if item["scope"] == "config"),
        None,
    )
    current_targets = _current_recovery_targets(installation)
    data_targets = current_targets | set(desired_data)
    for relative in data_targets:
        _safe_target(installation.data_path, relative)
    config_root = (installation.config_path or installation.data_path).resolve(strict=False)
    config_root.mkdir(parents=True, exist_ok=True)
    preferences_target = _safe_target(config_root, Path("cura.cfg")) if saved_preferences else None
    backup_path, existed = _backup_restore_targets(
        installation,
        restore_id,
        data_targets,
        preferences_target,
    )
    removed_files = 0
    try:
        for relative, content in desired_data.items():
            _atomic_write(_safe_target(installation.data_path, relative), content)
        for relative in current_targets - set(desired_data):
            _safe_target(installation.data_path, relative).unlink(missing_ok=True)
            removed_files += 1
        preferences_merged = saved_preferences is not None
        if saved_preferences is not None and preferences_target is not None:
            try:
                current_preferences = preferences_target.read_text(encoding="utf-8")
            except FileNotFoundError:
                current_preferences = ""
            merged = _merge_preferences(current_preferences, saved_preferences)
            _atomic_write(preferences_target, merged)
    except Exception:
        _restore_failed_recovery(
            installation,
            backup_path,
            data_targets,
            preferences_target,
            existed,
        )
        raise
    raw_plugins = payload.get("plugins")
    plugin_items = raw_plugins if isinstance(raw_plugins, list) else []
    expected_plugins = {str(item.get("package_id")) for item in plugin_items if isinstance(item, dict)}
    current_plugins = {str(item["package_id"]) for item in _plugin_inventory(installation)}
    return {
        "installation_id": installation.installation_id,
        "version": installation.version,
        "status": "restored",
        "restored_files": len(desired_data) + int(saved_preferences is not None),
        "removed_files": removed_files,
        "preferences_merged": preferences_merged,
        "backup_id": f"{restore_id}/{installation.installation_id}",
        "missing_plugins": sorted(expected_plugins - current_plugins)[:RECOVERY_PLUGIN_LIMIT],
    }
