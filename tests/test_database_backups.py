"""Canonical PostgreSQL backup archive and restore-staging tests."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from testcontainers.community.postgres import PostgresContainer

from filament_manager.config import get_settings
from filament_manager.services import database_backups
from filament_manager.services.database_backups import DatabaseBackupError


def _archive_bytes(
    *,
    backup_id: UUID | None = None,
    created_at: datetime | None = None,
    extra_member: str | None = None,
    dump: bytes = b"PGDMP\x01\x0fcanonical-data",
) -> bytes:
    archive_id = backup_id or uuid4()
    timestamp = created_at or datetime.now(UTC)
    manifest = {
        "schema_version": 1,
        "product": "Filament Manager",
        "archive_type": "canonical_postgresql",
        "backup_id": str(archive_id),
        "created_at": timestamp.isoformat(),
        "application_version": "0.6.1",
        "database_revision": "a9b0c1d2e345",
        "trigger": "automatic",
        "dump_format": "postgresql-custom",
        "dump_member": "database.dump",
        "dump_size_bytes": len(dump),
        "dump_sha256": hashlib.sha256(dump).hexdigest(),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("database.dump", dump)
        if extra_member:
            archive.writestr(extra_member, b"unsafe")
    return output.getvalue()


def _configure_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "database-backups"
    monkeypatch.setattr(database_backups, "backup_root", lambda: root)
    return root


def _store_archive(root: Path, data: bytes, category: str = "automatic") -> Path:
    directory = root / category
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"filament-manager-backup-20260828T010203Z-{uuid4().hex[:8]}.zip"
    path.write_bytes(data)
    return path


def test_validates_and_lists_strict_filament_manager_zip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _configure_root(monkeypatch, tmp_path)
    backup_id = uuid4()
    path = _store_archive(root, _archive_bytes(backup_id=backup_id))

    archive = database_backups.validate_backup_archive(path, storage_kind="automatic")

    assert archive.id == backup_id
    assert archive.application_version == "0.6.1"
    assert archive.storage_kind == "automatic"
    assert database_backups.list_backup_archives() == [archive]


@pytest.mark.parametrize("extra_member", ["../escape", "nested/file", "unexpected.txt"])
def test_rejects_archives_with_extra_or_unsafe_members(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extra_member: str,
) -> None:
    root = _configure_root(monkeypatch, tmp_path)
    path = _store_archive(root, _archive_bytes(extra_member=extra_member))

    with pytest.raises(DatabaseBackupError, match="unsupported file layout"):
        database_backups.validate_backup_archive(path, storage_kind="automatic")


def test_rejects_non_postgresql_dump_even_with_matching_checksum(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _configure_root(monkeypatch, tmp_path)
    path = _store_archive(root, _archive_bytes(dump=b"not-a-postgresql-dump"))

    with pytest.raises(DatabaseBackupError, match="PostgreSQL custom dump"):
        database_backups.validate_backup_archive(path, storage_kind="automatic")


def test_import_deduplicates_and_automatic_retention_does_not_delete_imports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _configure_root(monkeypatch, tmp_path)
    imported_data = _archive_bytes()
    first = database_backups.import_backup_archive(io.BytesIO(imported_data))
    second = database_backups.import_backup_archive(io.BytesIO(imported_data))
    assert first.id == second.id

    now = datetime.now(UTC)
    for index in range(3):
        _store_archive(
            root,
            _archive_bytes(created_at=now - timedelta(hours=index)),
            category="automatic",
        )
    database_backups.prune_automatic_archives(2)

    archives = database_backups.list_backup_archives()
    assert len([item for item in archives if item.storage_kind == "automatic"]) == 2
    assert len([item for item in archives if item.storage_kind == "imported"]) == 1


@pytest.mark.asyncio
async def test_streamed_import_retains_complete_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Retain a raw authenticated upload without buffering it in request memory."""

    _configure_root(monkeypatch, tmp_path)
    archive_data = _archive_bytes()

    async def chunks():
        for offset in range(0, len(archive_data), 17):
            yield archive_data[offset : offset + 17]

    imported = await database_backups.import_backup_stream(chunks())

    assert imported.storage_kind == "imported"
    assert imported.archive_sha256 == hashlib.sha256(archive_data).hexdigest()


def test_prepare_restore_uses_exact_validated_archive_and_can_be_cancelled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _configure_root(monkeypatch, tmp_path)
    backup_id = uuid4()
    _store_archive(root, _archive_bytes(backup_id=backup_id))

    result = database_backups.prepare_restore(backup_id, requested_by=uuid4())

    assert result["status"] == "pending_maintenance"
    assert result["backup_id"] == backup_id
    assert database_backups.pending_restore() == {
        "status": "pending",
        "request_id": str(result["request_id"]),
        "backup_id": str(backup_id),
        "requested_at": result["requested_at"],
    }
    assert database_backups.cancel_pending_restore() is True
    assert database_backups.pending_restore() is None


@pytest.mark.parametrize(
    ("stderr", "safe_message"),
    (
        (
            b"pg_dump: error: aborting because of server version mismatch\n"
            b"pg_dump: detail: server version: 18.2; pg_dump version: 17.5",
            "backup tools are older than the database server",
        ),
        (b"password authentication failed for user secret-user", "database rejected the credentials"),
        (b"could not connect to server: Connection refused", "database could not be reached"),
    ),
)
def test_postgresql_command_reports_only_classified_safe_failures(
    monkeypatch: pytest.MonkeyPatch,
    stderr: bytes,
    safe_message: str,
) -> None:
    """Diagnostics must be actionable without returning raw PostgreSQL output."""

    monkeypatch.setattr(database_backups, "_database_environment", lambda: {})
    monkeypatch.setattr(
        database_backups.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr=stderr),
    )

    with pytest.raises(DatabaseBackupError, match=safe_message) as caught:
        database_backups._run_postgresql_command(["pg_dump"])

    assert "secret-user" not in str(caught.value)
    assert "18.2" not in str(caught.value)


def test_automatic_backup_failures_use_bounded_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed dump must not be respawned by every one-minute worker pass."""

    _configure_root(monkeypatch, tmp_path)
    before = datetime.now(UTC)
    database_backups.record_backup_failure()
    first = database_backups.backup_status()
    database_backups.record_backup_failure()
    second = database_backups.backup_status()

    assert first["consecutive_failures"] == 1
    assert second["consecutive_failures"] == 2
    first_retry = datetime.fromisoformat(str(first["next_retry_at"]))
    second_retry = datetime.fromisoformat(str(second["next_retry_at"]))
    assert timedelta(minutes=14) < first_retry - before <= timedelta(minutes=16)
    assert timedelta(minutes=29) < second_retry - before <= timedelta(minutes=31)


@pytest.mark.asyncio
async def test_automatic_backup_is_deferred_while_a_print_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Database dumps must not compete with Klipper host timing during motion."""

    class ActivePrintSession:
        async def scalar(self, _query: object) -> UUID:
            return uuid4()

    async def policy(_session: object) -> database_backups.BackupPolicy:
        return database_backups.BackupPolicy()

    monkeypatch.setattr(database_backups, "get_backup_policy", policy)

    due, returned_policy = await database_backups.backup_is_due(ActivePrintSession())  # type: ignore[arg-type]

    assert due is False
    assert returned_policy.enabled is True


@pytest.mark.integration
def test_real_postgresql_backup_and_restore_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Exercise the exact pg_dump, ZIP, and pg_restore recovery path.

    PostgreSQL refuses a dump when the client is older than the server. Match
    the disposable server to the available test client's major version; the
    production-image contract separately installs PostgreSQL client 18 so it
    can dump supported older PostgreSQL servers as well as version 18.
    """

    pg_dump_path = shutil.which("pg_dump")
    assert pg_dump_path is not None
    version_output = subprocess.run(  # noqa: S603 - resolved test dependency.
        [pg_dump_path, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    version_match = re.search(r"PostgreSQL\)\s+(\d+)", version_output)
    assert version_match is not None
    client_major = version_match.group(1)

    with PostgresContainer(f"postgres:{client_major}-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", database_url)
        get_settings.cache_clear()
        command.upgrade(Config("alembic.ini"), "head")
        settings = get_settings().model_copy(
            update={
                "app": get_settings().app.model_copy(update={"data_dir": tmp_path}),
            }
        )
        monkeypatch.setattr(database_backups, "get_settings", lambda: settings)

        engine = create_engine(database_url)
        marker_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO application_settings (
                        id, key, value, record_version, updated_by, created_at, updated_at
                    ) VALUES (
                        :id, 'backup-round-trip', CAST(:value AS jsonb), 1, NULL,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": marker_id, "value": json.dumps({"state": "before"})},
            )

        archive = database_backups.create_backup_archive("manual")
        database_backups.prepare_restore(archive.id, requested_by=uuid4())

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE application_settings SET value = CAST(:value AS jsonb) WHERE id = :id"),
                {"id": marker_id, "value": json.dumps({"state": "after"})},
            )
        engine.dispose()

        restored = database_backups.restore_pending_backup()

        verification_engine = create_engine(database_url)
        try:
            with verification_engine.connect() as connection:
                marker = connection.scalar(
                    text("SELECT value->>'state' FROM application_settings WHERE id = :id"),
                    {"id": marker_id},
                )
                restore_audit_count = connection.scalar(
                    text("SELECT count(*) FROM audit_events WHERE action = 'database.backup.restore'")
                )
        finally:
            verification_engine.dispose()
            get_settings.cache_clear()

        assert restored.id == archive.id
        assert marker == "before"
        assert restore_audit_count == 1
        assert database_backups.pending_restore() is None
