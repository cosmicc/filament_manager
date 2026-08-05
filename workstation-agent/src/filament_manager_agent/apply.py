"""Atomic Cura file installation, manifest tracking, backup, and rollback."""

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from .config import data_path
from .discovery import discover_installations
from .models import CuraInstallation
from .render import RenderedDeployment

MANIFEST_PATH = Path(".filament-manager") / "manifest.json"


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
    if not manifest or manifest.get("profile_checksum") != checksum:
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
    return True


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
    relative_targets = list(rendered.files)
    for relative in relative_targets:
        _safe_target(root, relative)
    backup_path, existed = _backup(root, deployment_id, installation.installation_id, relative_targets)
    try:
        for relative, content in rendered.files.items():
            _atomic_write(_safe_target(root, relative), content)
        manifest = {
            "schema_version": 1,
            "deployment_id": deployment_id,
            "profile_checksum": profile_checksum,
            "installed_at": datetime.now(UTC).isoformat(),
            "cura_version": installation.version,
            "machine_id": rendered.machine.machine_id,
            "backup_path": str(backup_path),
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
        raw_file_names = manifest.get("files")
        file_names: dict[str, object] = raw_file_names if isinstance(raw_file_names, dict) else {}
        targets = [Path(value) for value in file_names]
        with zipfile.ZipFile(backup_path) as archive:
            metadata = json.loads(archive.read(".filament-manager-backup.json"))
        existed = {Path(value) for value in metadata.get("existed", [])}
        _restore_backup(installation.data_path, backup_path, targets, existed)
        restored.append(f"Cura {installation.version}")
    if not restored:
        raise RuntimeError("The backup exists, but its Cura data directory was not detected.")
    return restored
