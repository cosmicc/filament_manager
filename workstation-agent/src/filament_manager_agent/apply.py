"""Atomic Cura file installation, manifest tracking, backup, and rollback."""

import hashlib
import json
import os
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from .config import data_path
from .discovery import discover_installations
from .models import CuraInstallation
from .quality_profiles import plan_quality_profile_cleanup, quality_profiles_are_clean
from .render import RenderedDeployment

MANIFEST_PATH = Path(".filament-manager") / "manifest.json"
MATERIAL_SETTINGS_STATUS_PATH = (
    Path("plugins")
    / "FilamentManagerVisibility"
    / "FilamentManagerVisibility"
    / "material-settings-status.json"
)
MATERIAL_SETTINGS_STATUS_SCHEMA_VERSION = 1
DEPLOYMENT_RENDERER_REVISION = 10


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _deployment_key(value: str) -> str:
    """Canonicalize an externally sourced deployment identity before path use."""

    try:
        return str(UUID(value))
    except ValueError as error:
        raise RuntimeError("Deployment ID must be a UUID.") from error


def _safe_target(root: Path, relative: Path) -> Path:
    """Resolve a controlled relative target and reject links or root escapes."""

    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("A rendered Cura path escaped its installation root.")
    root_resolved = root.resolve(strict=True)
    current = root_resolved
    for component in relative.parts[:-1]:
        current = current / component
        if current.exists() and current.is_symlink():
            raise RuntimeError(f"Refusing to write through symbolic link: {relative}")
    target = root_resolved / relative
    if target.exists() and target.is_symlink():
        raise RuntimeError(f"Refusing to replace symbolic link: {relative}")
    if not target.resolve(strict=False).is_relative_to(root_resolved):
        raise ValueError("A rendered Cura path escaped its installation root.")
    return target


def _atomic_write(target: Path, content: bytes) -> None:
    """Write, sync, and atomically replace one same-filesystem file."""

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _manifest(root: Path) -> dict[str, Any] | None:
    path = root / MANIFEST_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _already_current(root: Path, checksum: str) -> bool:
    manifest = _manifest(root)
    if (
        not manifest
        or manifest.get("library_checksum") != checksum
        or manifest.get("renderer_revision") != DEPLOYMENT_RENDERER_REVISION
    ):
        return False
    files = manifest.get("files")
    if not isinstance(files, dict):
        return False
    for relative_name, expected in files.items():
        if not isinstance(relative_name, str) or not isinstance(expected, str):
            return False
        target = _safe_target(root, Path(relative_name))
        try:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            return False
        if actual != expected:
            return False
    desired_materials = {
        relative_name
        for relative_name in files
        if PurePosixPath(relative_name).parent.as_posix() == "materials"
    }
    actual_materials = {
        PurePosixPath("materials", path.name).as_posix()
        for path in (root / "materials").glob("*.xml.fdm_material")
        if path.is_file()
    }
    if actual_materials != desired_materials:
        return False
    raw_cleanup_keys = manifest.get(
        "cleanup_material_setting_keys",
        manifest.get("managed_material_setting_keys"),
    )
    if not isinstance(raw_cleanup_keys, list) or not raw_cleanup_keys:
        return False
    if any(not isinstance(key, str) for key in raw_cleanup_keys):
        return False
    cleanup_keys = frozenset(raw_cleanup_keys)
    if len(cleanup_keys) != len(raw_cleanup_keys):
        return False
    if not quality_profiles_are_clean(root, cleanup_keys):
        return False
    return True


def managed_library_checksum(root: Path) -> str | None:
    """Return the verified installed library checksum, or None after any drift."""

    manifest = _manifest(root)
    checksum = manifest.get("library_checksum") if manifest else None
    if not isinstance(checksum, str) or len(checksum) != 64:
        return None
    return checksum if _already_current(root, checksum) else None


def material_settings_sync_status(root: Path) -> dict[str, object]:
    """Return a sanitized, manifest-bound Cura material-setting verification receipt."""

    manifest = _manifest(root)
    raw_expected = manifest.get("managed_material_setting_keys") if manifest else None
    if (
        not isinstance(raw_expected, list)
        or not raw_expected
        or any(
            not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key) for key in raw_expected
        )
    ):
        return {
            "status": "not_deployed",
            "expected_count": 0,
            "exposed_count": 0,
            "missing_keys": [],
            "unexpected_keys": [],
            "material_settings_plugin_ready": False,
            "klipper_settings_plugin_ready": False,
            "catalog_checksum": None,
            "verified_at": None,
        }
    expected = frozenset(raw_expected)
    if len(expected) != len(raw_expected):
        return {
            "status": "invalid",
            "expected_count": len(expected),
            "exposed_count": 0,
            "missing_keys": sorted(expected),
            "unexpected_keys": [],
            "material_settings_plugin_ready": False,
            "klipper_settings_plugin_ready": False,
            "catalog_checksum": None,
            "verified_at": None,
        }
    expected_checksum = hashlib.sha256("\n".join(sorted(expected)).encode("utf-8")).hexdigest()
    waiting = {
        "status": "waiting_for_cura",
        "expected_count": len(expected),
        "exposed_count": 0,
        "missing_keys": sorted(expected),
        "unexpected_keys": [],
        "material_settings_plugin_ready": False,
        "klipper_settings_plugin_ready": False,
        "catalog_checksum": expected_checksum,
        "verified_at": None,
    }
    try:
        status_path = _safe_target(root, MATERIAL_SETTINGS_STATUS_PATH)
        if status_path.stat().st_size > 32 * 1024:
            return {**waiting, "status": "invalid"}
        receipt = json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return waiting
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError, ValueError):
        return {**waiting, "status": "invalid"}
    if not isinstance(receipt, dict):
        return {**waiting, "status": "invalid"}
    if (
        receipt.get("schema_version") != MATERIAL_SETTINGS_STATUS_SCHEMA_VERSION
        or receipt.get("catalog_checksum") != expected_checksum
    ):
        return waiting
    raw_missing = receipt.get("missing_keys")
    raw_unexpected = receipt.get("unexpected_keys")
    if (
        not isinstance(raw_missing, list)
        or not isinstance(raw_unexpected, list)
        or len(raw_missing) > len(expected)
        or len(raw_unexpected) > 100
        or any(not isinstance(key, str) for key in [*raw_missing, *raw_unexpected])
    ):
        return {**waiting, "status": "invalid"}
    missing = frozenset(raw_missing)
    unexpected = frozenset(raw_unexpected)
    if (
        len(missing) != len(raw_missing)
        or len(unexpected) != len(raw_unexpected)
        or not missing <= expected
        or any(not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key) for key in unexpected)
    ):
        return {**waiting, "status": "invalid"}
    exposed_count = receipt.get("exposed_count")
    plugin_ready = receipt.get("material_settings_plugin_ready")
    klipper_ready = receipt.get("klipper_settings_plugin_ready")
    receipt_status = receipt.get("status")
    verified_at = receipt.get("verified_at")
    if (
        receipt.get("expected_count") != len(expected)
        or exposed_count != len(expected) - len(missing)
        or not isinstance(plugin_ready, bool)
        or not isinstance(klipper_ready, bool)
        or receipt_status not in {"healthy", "degraded", "waiting_for_machine"}
        or not isinstance(verified_at, str)
        or len(verified_at) > 64
    ):
        return {**waiting, "status": "invalid"}
    try:
        verified = datetime.fromisoformat(verified_at)
    except ValueError:
        return {**waiting, "status": "invalid"}
    if verified.tzinfo is None:
        return {**waiting, "status": "invalid"}
    if receipt_status == "healthy" and (missing or unexpected or not plugin_ready or not klipper_ready):
        return {**waiting, "status": "invalid"}
    return {
        "status": receipt_status,
        "expected_count": len(expected),
        "exposed_count": exposed_count,
        "missing_keys": sorted(missing),
        "unexpected_keys": sorted(unexpected),
        "material_settings_plugin_ready": plugin_ready,
        "klipper_settings_plugin_ready": klipper_ready,
        "catalog_checksum": expected_checksum,
        "verified_at": verified.isoformat(),
    }


def _backup(
    root: Path,
    deployment_id: str,
    installation_id: str,
    targets: list[Path],
) -> tuple[Path, set[Path]]:
    backup_directory = data_path() / "backups" / deployment_id
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / f"{installation_id}.zip"
    existed: set[Path] = set()
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in [*targets, MANIFEST_PATH]:
            target = _safe_target(root, relative)
            if target.is_file():
                existed.add(relative)
                archive.writestr(PurePosixPath(relative).as_posix(), target.read_bytes())
        archive.writestr(
            ".filament-manager-backup.json",
            json.dumps(
                {
                    "root_version": root.name,
                    "existed": sorted(PurePosixPath(item).as_posix() for item in existed),
                    "managed_targets": sorted(PurePosixPath(item).as_posix() for item in targets),
                    "created_at": datetime.now(UTC).isoformat(),
                },
                sort_keys=True,
            ),
        )
    return backup_path, existed


def _restore_backup(root: Path, backup_path: Path, managed_targets: list[Path], existed: set[Path]) -> None:
    """Restore only known targets, removing newly-created managed files."""

    with zipfile.ZipFile(backup_path) as archive:
        archive_names = set(archive.namelist())
        for relative in [*managed_targets, MANIFEST_PATH]:
            target = _safe_target(root, relative)
            archive_name = PurePosixPath(relative).as_posix()
            if relative in existed and archive_name in archive_names:
                _atomic_write(target, archive.read(archive_name))
            elif relative not in existed:
                target.unlink(missing_ok=True)


def _quarantine_profile(
    installation: CuraInstallation,
    deployment_id: str,
    relative: Path,
    content: bytes,
) -> str:
    """Copy one corrupt profile outside Cura before removing its active file."""

    installation_key = hashlib.sha256(installation.installation_id.encode("utf-8")).hexdigest()[:16]
    quarantine_root = data_path() / "quarantine" / deployment_id / installation_key
    quarantine_target = quarantine_root / relative
    _atomic_write(quarantine_target, content)
    return f"{deployment_id}/{installation_key}/{PurePosixPath(relative).as_posix()}"


def apply_rendered(
    installation: CuraInstallation,
    deployment_id: str,
    profile_checksum: str,
    rendered: RenderedDeployment,
) -> dict[str, object]:
    """Back up and atomically install one rendered deployment."""

    root = installation.data_path.resolve(strict=True)
    deployment_id = _deployment_key(deployment_id)
    if _already_current(root, profile_checksum):
        return {
            "installation_id": installation.installation_id,
            "version": installation.version,
            "machine": rendered.machine.display_name,
            "status": "already_current",
            "warnings": rendered.warnings,
        }
    quality_cleanup = plan_quality_profile_cleanup(
        root,
        rendered.cleanup_material_setting_keys,
    )
    desired_targets = set(rendered.files)
    cleanup_targets = {
        Path("materials") / path.name for path in (root / "materials").glob("*.xml.fdm_material")
    } - desired_targets
    previous_manifest = _manifest(root) or {}
    previous_files = previous_manifest.get("files")
    if isinstance(previous_files, dict):
        cleanup_targets.update(Path(value) for value in previous_files if Path(value) not in desired_targets)
    quality_targets = set(quality_cleanup.replacements) | set(quality_cleanup.quarantines)
    relative_targets = sorted(
        desired_targets | cleanup_targets | quality_targets,
        key=lambda item: item.as_posix(),
    )
    for relative in relative_targets:
        _safe_target(root, relative)
    backup_path, existed = _backup(root, deployment_id, installation.installation_id, relative_targets)
    try:
        for relative, content in rendered.files.items():
            _atomic_write(_safe_target(root, relative), content)
        for relative, content in quality_cleanup.replacements.items():
            _atomic_write(_safe_target(root, relative), content)
        quarantined_profiles: list[str] = []
        for relative, content in quality_cleanup.quarantines.items():
            quarantined_profiles.append(_quarantine_profile(installation, deployment_id, relative, content))
            _safe_target(root, relative).unlink(missing_ok=True)
        for relative in cleanup_targets:
            _safe_target(root, relative).unlink(missing_ok=True)
        manifest = {
            "schema_version": 3,
            "renderer_revision": DEPLOYMENT_RENDERER_REVISION,
            "deployment_id": deployment_id,
            "library_checksum": profile_checksum,
            "installed_at": datetime.now(UTC).isoformat(),
            "cura_version": installation.version,
            "machine_id": rendered.machine.machine_id,
            "backup_path": str(backup_path),
            "managed_material_setting_keys": sorted(rendered.managed_material_setting_keys),
            "cleanup_material_setting_keys": sorted(rendered.cleanup_material_setting_keys),
            "quality_profile_cleanup": {
                "sanitized_profiles": len(quality_cleanup.replacements),
                "repaired_profiles": quality_cleanup.repaired_profile_count,
                "removed_material_settings": quality_cleanup.removed_setting_count,
                "quarantined_profiles": len(quality_cleanup.quarantines),
            },
            "files": {
                PurePosixPath(relative).as_posix(): _sha256(content)
                for relative, content in rendered.files.items()
            },
        }
        _atomic_write(
            _safe_target(root, MANIFEST_PATH),
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    except Exception:
        _restore_backup(root, backup_path, relative_targets, existed)
        raise
    return {
        "installation_id": installation.installation_id,
        "version": installation.version,
        "machine": rendered.machine.display_name,
        "status": "installed",
        "managed_files": len(rendered.files),
        "backup_id": f"{deployment_id}/{installation.installation_id}",
        "quality_profiles_sanitized": len(quality_cleanup.replacements),
        "quality_profiles_repaired": quality_cleanup.repaired_profile_count,
        "quality_profile_settings_removed": quality_cleanup.removed_setting_count,
        "quality_profiles_quarantined": len(quality_cleanup.quarantines),
        "quarantine_ids": quarantined_profiles,
        "warnings": rendered.warnings,
    }


def rollback(deployment_id: str) -> list[str]:
    """Restore all local installations represented by a deployment backup."""

    safe_deployment_id = _deployment_key(deployment_id)
    backup_directory = data_path() / "backups" / safe_deployment_id
    if not backup_directory.is_dir():
        raise RuntimeError(f"No backup exists for deployment {deployment_id}.")
    restored: list[str] = []
    installations = {item.installation_id: item for item in discover_installations()}
    for backup_path in sorted(backup_directory.glob("*.zip")):
        installation = installations.get(backup_path.stem)
        if installation is None:
            continue
        manifest = _manifest(installation.data_path) or {}
        with zipfile.ZipFile(backup_path) as archive:
            metadata = json.loads(archive.read(".filament-manager-backup.json"))
        targets = [Path(value) for value in metadata.get("managed_targets", [])]
        if not targets:
            raw_file_names = manifest.get("files")
            file_names: dict[str, object] = raw_file_names if isinstance(raw_file_names, dict) else {}
            targets = [Path(value) for value in file_names]
        existed = {Path(value) for value in metadata.get("existed", [])}
        _restore_backup(installation.data_path, backup_path, targets, existed)
        restored.append(f"Cura {installation.version}")
    if not restored:
        raise RuntimeError("The backup exists, but its Cura data directory was not detected.")
    return restored
