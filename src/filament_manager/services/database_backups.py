"""Create, validate, retain, import, and restore canonical database backups.

Backups intentionally contain only the Filament Manager PostgreSQL database.
Spoolman remains independently credentialed and is never accessed here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from collections.abc import AsyncIterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager import __version__
from filament_manager.config import get_settings
from filament_manager.models.operations import ApplicationSetting

BACKUP_POLICY_KEY = "database_backup"
BACKUP_ARCHIVE_SCHEMA_VERSION = 1
BACKUP_STATUS_SCHEMA_VERSION = 1
BACKUP_ROOT_NAME = "database-backups"
BACKUP_MEMBER_NAME = "database.dump"
MANIFEST_MEMBER_NAME = "manifest.json"
PENDING_RESTORE_NAME = "pending-restore.json"
RESTORE_RECEIPT_NAME = "last-restore.json"
STATUS_NAME = "status.json"
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
MAX_DUMP_BYTES = 16 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 32 * 1024
READ_CHUNK_BYTES = 1024 * 1024
BACKUP_LOCK_KEY = 7_162_159_241_176_977_409
ARCHIVE_NAME_PATTERN = re.compile(r"^filament-manager-backup-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\.zip$")
SEMANTIC_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_VALIDATED_ARCHIVE_CACHE: dict[tuple[str, str, int, int], BackupArchive] = {}


class DatabaseBackupError(RuntimeError):
    """A bounded database-backup failure safe for API and CLI presentation."""


@dataclass(frozen=True)
class BackupPolicy:
    """Administrator-controlled automatic-backup schedule and retention."""

    enabled: bool = True
    interval_hours: int = 24
    retention_count: int = 10
    record_version: int = 0


@dataclass(frozen=True)
class BackupArchive:
    """Validated archive metadata safe to return through Diagnostics."""

    id: UUID
    created_at: datetime
    application_version: str
    database_revision: str
    trigger: str
    storage_kind: str
    filename: str
    size_bytes: int
    archive_sha256: str
    dump_sha256: str


def backup_root() -> Path:
    """Return the private canonical-backup directory under application data."""

    return get_settings().app.data_dir / BACKUP_ROOT_NAME


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise DatabaseBackupError("The configured database backup directory is unsafe.")
    path.chmod(0o700)


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    """Write one bounded private JSON control file atomically."""

    _ensure_private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _database_environment() -> dict[str, str]:
    """Build libpq environment values without exposing credentials in argv."""

    url = make_url(get_settings().database.resolved_url())
    environment = os.environ.copy()
    for key in (
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
        "PGSSLMODE",
    ):
        environment.pop(key, None)
    if url.host:
        environment["PGHOST"] = url.host
    if url.port:
        environment["PGPORT"] = str(url.port)
    if url.database:
        environment["PGDATABASE"] = url.database
    if url.username:
        environment["PGUSER"] = url.username
    if url.password:
        environment["PGPASSWORD"] = url.password
    sslmode = url.query.get("sslmode")
    if isinstance(sslmode, str) and sslmode:
        environment["PGSSLMODE"] = sslmode
    return environment


def _run_postgresql_command(arguments: list[str], *, timeout_seconds: int = 3600) -> None:
    """Run one fixed PostgreSQL client command without retaining sensitive stderr."""

    try:
        completed = subprocess.run(  # noqa: S603 - argv is fixed by trusted application code.
            arguments,
            check=False,
            env=_database_environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as error:
        raise DatabaseBackupError(
            "The PostgreSQL backup tools are unavailable in this application image."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise DatabaseBackupError("The PostgreSQL backup operation timed out.") from error
    if completed.returncode != 0:
        raise DatabaseBackupError("The PostgreSQL backup operation failed.")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _current_database_revision() -> str:
    """Read the current Alembic revision without exposing the database URL."""

    import psycopg

    url = get_settings().database.resolved_url().replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        with psycopg.connect(url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                row = cursor.fetchone()
    except psycopg.Error as error:
        raise DatabaseBackupError("The current database revision could not be read.") from error
    if row is None or not isinstance(row[0], str) or not row[0]:
        raise DatabaseBackupError("The current database revision is unavailable.")
    return row[0][:64]


def _assert_database_quiescent() -> None:
    """Refuse restoration while any other database session remains connected."""

    import psycopg

    url = get_settings().database.resolved_url().replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        with psycopg.connect(url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT count(*)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid <> pg_backend_pid()
                    """
                )
                row = cursor.fetchone()
    except psycopg.Error as error:
        raise DatabaseBackupError("Database maintenance readiness could not be verified.") from error
    if row is None or not isinstance(row[0], int):
        raise DatabaseBackupError("Database maintenance readiness could not be verified.")
    if row[0] != 0:
        raise DatabaseBackupError(
            "Other database sessions are still connected. Stop web and worker before restoring."
        )


def _archive_filename(created_at: datetime, archive_id: UUID) -> str:
    return f"filament-manager-backup-{created_at.strftime('%Y%m%dT%H%M%SZ')}-{archive_id.hex[:8]}.zip"


def create_backup_archive(trigger: Literal["automatic", "manual", "pre_restore"]) -> BackupArchive:
    """Create one atomic ZIP containing a PostgreSQL custom-format dump and manifest."""

    root = backup_root()
    category = "automatic" if trigger == "automatic" else "manual"
    destination_directory = root / category
    temporary_directory = root / ".tmp"
    _ensure_private_directory(destination_directory)
    _ensure_private_directory(temporary_directory)
    created_at = datetime.now(UTC)
    archive_id = uuid4()
    filename = _archive_filename(created_at, archive_id)
    destination = destination_directory / filename

    with tempfile.TemporaryDirectory(prefix="create-", dir=temporary_directory) as temporary_name:
        workspace = Path(temporary_name)
        workspace.chmod(0o700)
        dump_path = workspace / BACKUP_MEMBER_NAME
        _run_postgresql_command(
            [
                "pg_dump",
                "--format=custom",
                "--compress=0",
                "--no-owner",
                "--no-privileges",
                "--lock-wait-timeout=30s",
                "--file",
                str(dump_path),
            ]
        )
        dump_size = dump_path.stat().st_size
        if dump_size <= 0 or dump_size > MAX_DUMP_BYTES:
            raise DatabaseBackupError("The generated database dump has an invalid size.")
        dump_sha256 = _sha256_file(dump_path)
        manifest: dict[str, object] = {
            "schema_version": BACKUP_ARCHIVE_SCHEMA_VERSION,
            "product": "Filament Manager",
            "archive_type": "canonical_postgresql",
            "backup_id": str(archive_id),
            "created_at": created_at.isoformat(),
            "application_version": __version__,
            "database_revision": _current_database_revision(),
            "trigger": trigger,
            "dump_format": "postgresql-custom",
            "dump_member": BACKUP_MEMBER_NAME,
            "dump_size_bytes": dump_size,
            "dump_sha256": dump_sha256,
        }
        archive_temporary = workspace / filename
        with zipfile.ZipFile(
            archive_temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            strict_timestamps=True,
        ) as archive:
            archive.writestr(
                MANIFEST_MEMBER_NAME,
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
            )
            archive.write(dump_path, BACKUP_MEMBER_NAME)
        archive_temporary.chmod(0o600)
        if archive_temporary.stat().st_size > MAX_ARCHIVE_BYTES:
            raise DatabaseBackupError("The generated database backup archive is too large.")
        archive_temporary.replace(destination)
        destination.chmod(0o600)

    validated = validate_backup_archive(destination, storage_kind=category)
    _write_backup_status(status="healthy", archive=validated)
    return validated


def _safe_zip_members(archive: zipfile.ZipFile) -> tuple[zipfile.ZipInfo, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) != 2 or {item.filename for item in infos} != {
        MANIFEST_MEMBER_NAME,
        BACKUP_MEMBER_NAME,
    }:
        raise DatabaseBackupError("The backup archive has an unsupported file layout.")
    indexed = {item.filename: item for item in infos}
    for info in infos:
        path = PurePosixPath(info.filename)
        mode = info.external_attr >> 16
        if (
            path.is_absolute()
            or len(path.parts) != 1
            or ".." in path.parts
            or info.flag_bits & 0x1
            or stat.S_ISLNK(mode)
            or info.is_dir()
        ):
            raise DatabaseBackupError("The backup archive contains an unsafe entry.")
    manifest_info = indexed[MANIFEST_MEMBER_NAME]
    dump_info = indexed[BACKUP_MEMBER_NAME]
    if manifest_info.file_size <= 0 or manifest_info.file_size > MAX_MANIFEST_BYTES:
        raise DatabaseBackupError("The backup manifest has an invalid size.")
    if dump_info.file_size <= 0 or dump_info.file_size > MAX_DUMP_BYTES:
        raise DatabaseBackupError("The database dump has an invalid size.")
    return manifest_info, dump_info


def validate_backup_archive(
    path: Path,
    *,
    storage_kind: str,
    use_cache: bool = False,
) -> BackupArchive:
    """Fully validate one local or uploaded backup archive without extracting paths."""

    if path.is_symlink() or not path.is_file():
        raise DatabaseBackupError("The database backup archive is unavailable.")
    file_stat = path.stat()
    size_bytes = file_stat.st_size
    if size_bytes <= 0 or size_bytes > MAX_ARCHIVE_BYTES:
        raise DatabaseBackupError("The database backup archive has an invalid size.")
    resolved_path = str(path.resolve())
    cache_key = (resolved_path, storage_kind, file_stat.st_mtime_ns, size_bytes)
    for stale_key in [
        key for key in _VALIDATED_ARCHIVE_CACHE if key[0] == resolved_path and key != cache_key
    ]:
        _VALIDATED_ARCHIVE_CACHE.pop(stale_key, None)
    if use_cache and (cached := _VALIDATED_ARCHIVE_CACHE.get(cache_key)) is not None:
        return cached
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            manifest_info, dump_info = _safe_zip_members(archive)
            with archive.open(manifest_info, mode="r") as source:
                manifest_raw = source.read(MAX_MANIFEST_BYTES + 1)
            if len(manifest_raw) > MAX_MANIFEST_BYTES:
                raise DatabaseBackupError("The backup manifest is too large.")
            manifest = json.loads(manifest_raw)
            if not isinstance(manifest, dict):
                raise DatabaseBackupError("The backup manifest is invalid.")
            expected = {
                "schema_version": BACKUP_ARCHIVE_SCHEMA_VERSION,
                "product": "Filament Manager",
                "archive_type": "canonical_postgresql",
                "dump_format": "postgresql-custom",
                "dump_member": BACKUP_MEMBER_NAME,
            }
            if any(manifest.get(key) != value for key, value in expected.items()):
                raise DatabaseBackupError("The file is not a supported Filament Manager backup.")
            if manifest.get("dump_size_bytes") != dump_info.file_size:
                raise DatabaseBackupError("The database dump size does not match its manifest.")
            dump_digest = hashlib.sha256()
            dump_prefix = b""
            with archive.open(dump_info, mode="r") as source:
                while chunk := source.read(READ_CHUNK_BYTES):
                    if len(dump_prefix) < 5:
                        dump_prefix = (dump_prefix + chunk)[:5]
                    dump_digest.update(chunk)
            if dump_prefix != b"PGDMP":
                raise DatabaseBackupError("The archive does not contain a PostgreSQL custom dump.")
            dump_sha256 = dump_digest.hexdigest()
            if manifest.get("dump_sha256") != dump_sha256:
                raise DatabaseBackupError("The database dump checksum does not match its manifest.")
            archive_id = UUID(str(manifest.get("backup_id")))
            created_at = datetime.fromisoformat(str(manifest.get("created_at")))
            if created_at.tzinfo is None:
                raise ValueError("created_at must include a timezone")
            application_version = str(manifest.get("application_version") or "")
            database_revision = str(manifest.get("database_revision") or "")
            trigger = str(manifest.get("trigger") or "")
            if (
                SEMANTIC_VERSION_PATTERN.fullmatch(application_version) is None
                or not 1 <= len(database_revision) <= 64
                or trigger not in {"automatic", "manual", "pre_restore"}
            ):
                raise DatabaseBackupError("The backup manifest contains invalid metadata.")
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError, ValueError) as error:
        if isinstance(error, DatabaseBackupError):
            raise
        raise DatabaseBackupError("The database backup archive is invalid.") from error
    validated = BackupArchive(
        id=archive_id,
        created_at=created_at.astimezone(UTC),
        application_version=application_version,
        database_revision=database_revision,
        trigger=trigger,
        storage_kind=storage_kind,
        filename=path.name,
        size_bytes=size_bytes,
        archive_sha256=_sha256_file(path),
        dump_sha256=dump_sha256,
    )
    _VALIDATED_ARCHIVE_CACHE[cache_key] = validated
    return validated


def _archive_directories() -> tuple[tuple[str, Path], ...]:
    root = backup_root()
    return (
        ("automatic", root / "automatic"),
        ("manual", root / "manual"),
        ("imported", root / "imported"),
    )


def list_backup_archives() -> list[BackupArchive]:
    """List only fully validated local archives and silently isolate malformed files."""

    archives: list[BackupArchive] = []
    for storage_kind, directory in _archive_directories():
        if not directory.exists() or directory.is_symlink() or not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_symlink() or not path.is_file() or not ARCHIVE_NAME_PATTERN.fullmatch(path.name):
                continue
            try:
                archives.append(validate_backup_archive(path, storage_kind=storage_kind, use_cache=True))
            except DatabaseBackupError:
                continue
    return sorted(archives, key=lambda item: item.created_at, reverse=True)


def archive_path(archive_id: UUID) -> tuple[BackupArchive, Path]:
    """Resolve one validated archive by manifest identity without accepting a path."""

    matches: list[tuple[BackupArchive, Path]] = []
    for archive in list_backup_archives():
        if archive.id != archive_id:
            continue
        directory = dict(_archive_directories())[archive.storage_kind]
        matches.append((archive, directory / archive.filename))
    if len(matches) != 1:
        raise DatabaseBackupError("The selected database backup is unavailable.")
    listed, path = matches[0]
    validated = validate_backup_archive(path, storage_kind=listed.storage_kind)
    if validated.id != listed.id:
        raise DatabaseBackupError("The selected database backup identity changed.")
    return validated, path


def prune_automatic_archives(retention_count: int) -> None:
    """Retain only the newest configured automatic archives."""

    automatic = [item for item in list_backup_archives() if item.storage_kind == "automatic"]
    directory = dict(_archive_directories())["automatic"]
    for archive in automatic[max(1, retention_count) :]:
        path = directory / archive.filename
        if path.is_file() and not path.is_symlink():
            path.unlink()


def _write_backup_status(*, status: str, archive: BackupArchive | None = None) -> None:
    payload: dict[str, object] = {
        "schema_version": BACKUP_STATUS_SCHEMA_VERSION,
        "status": status,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    if archive is not None:
        payload.update(
            {
                "last_success_at": archive.created_at.isoformat(),
                "last_backup_id": str(archive.id),
            }
        )
    _atomic_json(backup_root() / STATUS_NAME, payload)


def record_backup_failure() -> None:
    """Persist only a bounded failure state, never a command or database error body."""

    previous = backup_status()
    _atomic_json(
        backup_root() / STATUS_NAME,
        {
            "schema_version": BACKUP_STATUS_SCHEMA_VERSION,
            "status": "error",
            "checked_at": datetime.now(UTC).isoformat(),
            "last_success_at": previous.get("last_success_at"),
        },
    )


def backup_status() -> dict[str, object]:
    path = backup_root() / STATUS_NAME
    if not path.is_file() or path.is_symlink():
        return {"status": "never", "checked_at": None, "last_success_at": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "invalid", "checked_at": None, "last_success_at": None}
    if not isinstance(payload, dict) or payload.get("schema_version") != BACKUP_STATUS_SCHEMA_VERSION:
        return {"status": "invalid", "checked_at": None, "last_success_at": None}
    return {
        "status": str(payload.get("status") or "invalid")[:32],
        "checked_at": payload.get("checked_at"),
        "last_success_at": payload.get("last_success_at"),
    }


async def get_backup_policy(session: AsyncSession) -> BackupPolicy:
    setting = await session.scalar(
        select(ApplicationSetting).where(ApplicationSetting.key == BACKUP_POLICY_KEY)
    )
    if setting is None:
        return BackupPolicy()
    value = setting.value

    def bounded_integer(key: str, default: int, maximum: int) -> int:
        raw = value.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, (int, str)):
            return default
        try:
            parsed = int(raw)
        except ValueError:
            return default
        return max(1, min(parsed, maximum))

    return BackupPolicy(
        enabled=bool(value.get("enabled", True)),
        interval_hours=bounded_integer("interval_hours", 24, 24 * 30),
        retention_count=bounded_integer("retention_count", 10, 100),
        record_version=setting.record_version,
    )


async def update_backup_policy(
    session: AsyncSession,
    *,
    enabled: bool,
    interval_hours: int,
    retention_count: int,
    expected_version: int,
    updated_by: UUID,
) -> BackupPolicy:
    """Save the automatic-backup policy with optimistic concurrency."""

    setting = await session.scalar(
        select(ApplicationSetting).where(ApplicationSetting.key == BACKUP_POLICY_KEY).with_for_update()
    )
    if setting is None:
        if expected_version != 0:
            raise DatabaseBackupError("The database backup schedule changed; refresh and try again.")
        setting = ApplicationSetting(
            key=BACKUP_POLICY_KEY,
            value={},
            record_version=1,
            updated_by=updated_by,
        )
        session.add(setting)
    else:
        if setting.record_version != expected_version:
            raise DatabaseBackupError("The database backup schedule changed; refresh and try again.")
        setting.record_version += 1
        setting.updated_by = updated_by
    setting.value = {
        "enabled": enabled,
        "interval_hours": interval_hours,
        "retention_count": retention_count,
    }
    await session.flush()
    return BackupPolicy(
        enabled=enabled,
        interval_hours=interval_hours,
        retention_count=retention_count,
        record_version=setting.record_version,
    )


async def backup_is_due(session: AsyncSession) -> tuple[bool, BackupPolicy]:
    policy = await get_backup_policy(session)
    if not policy.enabled:
        return False, policy
    automatic = [item for item in list_backup_archives() if item.storage_kind == "automatic"]
    if not automatic:
        return True, policy
    due_at = automatic[0].created_at + timedelta(hours=policy.interval_hours)
    return datetime.now(UTC) >= due_at, policy


async def acquire_backup_lock(session: AsyncSession) -> bool:
    acquired = await session.scalar(
        text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": BACKUP_LOCK_KEY}
    )
    return acquired is True


async def release_backup_lock(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": BACKUP_LOCK_KEY})


def _retain_imported_temporary(temporary: Path) -> BackupArchive:
    """Validate, deduplicate, and retain one completed private upload."""

    imported_directory = backup_root() / "imported"
    _ensure_private_directory(imported_directory)
    temporary.chmod(0o600)
    validated = validate_backup_archive(temporary, storage_kind="imported")
    for existing in list_backup_archives():
        if existing.archive_sha256 == validated.archive_sha256:
            return existing
        if existing.id == validated.id:
            raise DatabaseBackupError("A different database backup already uses this archive identity.")
    filename = _archive_filename(validated.created_at, validated.id)
    destination_path = imported_directory / filename
    if destination_path.exists():
        filename = _archive_filename(datetime.now(UTC), uuid4())
        destination_path = imported_directory / filename
    temporary.replace(destination_path)
    destination_path.chmod(0o600)
    return validate_backup_archive(destination_path, storage_kind="imported")


def import_backup_archive(source: BinaryIO) -> BackupArchive:
    """Stream, validate, deduplicate, and privately retain a file-like ZIP archive."""

    temporary_directory = backup_root() / ".tmp"
    _ensure_private_directory(temporary_directory)
    temporary = temporary_directory / f"upload-{uuid4().hex}.zip"
    total = 0
    try:
        with temporary.open("xb") as destination:
            while chunk := source.read(READ_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise DatabaseBackupError("The uploaded database backup is too large.")
                destination.write(chunk)
        return _retain_imported_temporary(temporary)
    finally:
        temporary.unlink(missing_ok=True)


async def import_backup_stream(chunks: AsyncIterable[bytes]) -> BackupArchive:
    """Write an authenticated request stream directly to private backup storage."""

    temporary_directory = backup_root() / ".tmp"
    await asyncio.to_thread(_ensure_private_directory, temporary_directory)
    temporary = temporary_directory / f"upload-{uuid4().hex}.zip"
    total = 0
    try:
        with temporary.open("xb") as destination:
            async for chunk in chunks:
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise DatabaseBackupError("The uploaded database backup is too large.")
                await asyncio.to_thread(destination.write, chunk)
        return await asyncio.to_thread(_retain_imported_temporary, temporary)
    finally:
        await asyncio.to_thread(temporary.unlink, missing_ok=True)


def pending_restore() -> dict[str, object] | None:
    path = backup_root() / PENDING_RESTORE_NAME
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "invalid"}
    if not isinstance(payload, dict):
        return {"status": "invalid"}
    return {
        "status": "pending",
        "request_id": payload.get("request_id"),
        "backup_id": payload.get("backup_id"),
        "requested_at": payload.get("requested_at"),
    }


def prepare_restore(archive_id: UUID, *, requested_by: UUID) -> dict[str, object]:
    """Stage one exact archive for the stopped-service restore command."""

    pending_path = backup_root() / PENDING_RESTORE_NAME
    if pending_path.exists():
        raise DatabaseBackupError("A database restore is already pending.")
    archive, path = archive_path(archive_id)
    request_id = uuid4()
    relative_path = path.relative_to(backup_root())
    payload: dict[str, object] = {
        "schema_version": 1,
        "request_id": str(request_id),
        "backup_id": str(archive.id),
        "archive_path": relative_path.as_posix(),
        "archive_sha256": archive.archive_sha256,
        "requested_by": str(requested_by),
        "requested_at": datetime.now(UTC).isoformat(),
    }
    _atomic_json(pending_path, payload)
    return {
        "status": "pending_maintenance",
        "request_id": request_id,
        "backup_id": archive.id,
        "requested_at": payload["requested_at"],
    }


def cancel_pending_restore() -> bool:
    path = backup_root() / PENDING_RESTORE_NAME
    if path.is_symlink():
        raise DatabaseBackupError("The pending database restore marker is unsafe.")
    existed = path.is_file()
    path.unlink(missing_ok=True)
    return existed


def _read_pending_restore_private() -> tuple[dict[str, object], BackupArchive, Path]:
    marker_path = backup_root() / PENDING_RESTORE_NAME
    if marker_path.is_symlink() or not marker_path.is_file():
        raise DatabaseBackupError("No pending database restore was prepared.")
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("invalid marker")
        relative = PurePosixPath(str(payload["archive_path"]))
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
            raise ValueError("unsafe archive path")
        path = backup_root().joinpath(*relative.parts)
        storage_kind = relative.parts[0]
        if storage_kind not in {"automatic", "manual", "imported"}:
            raise ValueError("invalid storage kind")
        archive = validate_backup_archive(path, storage_kind=storage_kind)
        if (
            str(archive.id) != str(payload["backup_id"])
            or archive.archive_sha256 != payload["archive_sha256"]
        ):
            raise ValueError("archive identity mismatch")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DatabaseBackupError("The pending database restore request is invalid.") from error
    return payload, archive, path


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = SEMANTIC_VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise DatabaseBackupError("The backup application version is invalid.")
    return tuple(int(group) for group in match.groups())  # type: ignore[return-value]


def restore_pending_backup() -> BackupArchive:
    """Apply the staged archive in one transaction while app services are stopped.

    The caller is responsible for stopping web and worker services. The command
    creates a pre-restore safety archive, restores with ownership/ACL suppression,
    and leaves the request in place if any step fails.
    """

    payload, archive, path = _read_pending_restore_private()
    if _version_tuple(archive.application_version) > _version_tuple(__version__):
        raise DatabaseBackupError(
            "This backup was created by a newer Filament Manager version. Upgrade before restoring it."
        )
    _assert_database_quiescent()
    create_backup_archive("pre_restore")
    _assert_database_quiescent()
    temporary_directory = backup_root() / ".tmp"
    _ensure_private_directory(temporary_directory)
    with tempfile.TemporaryDirectory(prefix="restore-", dir=temporary_directory) as temporary_name:
        workspace = Path(temporary_name)
        workspace.chmod(0o700)
        dump_path = workspace / BACKUP_MEMBER_NAME
        with zipfile.ZipFile(path, mode="r") as source_archive:
            with (
                source_archive.open(BACKUP_MEMBER_NAME, mode="r") as source,
                dump_path.open("xb") as destination,
            ):
                shutil.copyfileobj(source, destination, length=READ_CHUNK_BYTES)
        dump_path.chmod(0o600)
        if _sha256_file(dump_path) != archive.dump_sha256:
            raise DatabaseBackupError("The extracted database dump checksum is invalid.")
        _run_postgresql_command(
            [
                "pg_restore",
                "--exit-on-error",
                "--single-transaction",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                make_url(get_settings().database.resolved_url()).database or "",
                str(dump_path),
            ]
        )

    from sqlalchemy import create_engine

    from filament_manager.startup import upgrade_database

    upgrade_database(get_settings().database)
    engine = create_engine(get_settings().database.resolved_url())
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM user_sessions"))
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        id, actor_id, source, action, object_type, object_id,
                        before, after, metadata, correlation_id, occurred_at
                    ) VALUES (
                        :id, NULL, 'recovery', 'database.backup.restore',
                        'database_backup', NULL, NULL, NULL,
                        CAST(:metadata AS jsonb), :correlation_id, :occurred_at
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "metadata": json.dumps(
                        {
                            "backup_id": str(archive.id),
                            "request_id": str(payload["request_id"]),
                            "browser_sessions_revoked": True,
                        }
                    ),
                    "correlation_id": f"database-restore:{str(payload['request_id'])[:32]}",
                    "occurred_at": datetime.now(UTC),
                },
            )
    finally:
        engine.dispose()
    (backup_root() / PENDING_RESTORE_NAME).unlink()
    _atomic_json(
        backup_root() / RESTORE_RECEIPT_NAME,
        {
            "schema_version": 1,
            "status": "completed",
            "backup_id": str(archive.id),
            "request_id": payload["request_id"],
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )
    return archive


def archive_payload(archive: BackupArchive) -> dict[str, object]:
    """Convert archive metadata into a JSON-ready dictionary."""

    return asdict(archive)
