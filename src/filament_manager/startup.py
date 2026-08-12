"""Container entry point that safely upgrades the canonical schema before startup."""

import os
import sys
import time
from collections.abc import Sequence

import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

from filament_manager.config import DatabaseConfig, get_settings
from filament_manager.logging import configure_logging

logger = structlog.get_logger()

# A stable application-specific signed 64-bit PostgreSQL advisory-lock key. This is
# intentionally independent from database object identifiers and is never user input.
MIGRATION_LOCK_KEY = 7_162_159_241_176_977_408
MIGRATING_COMMANDS = frozenset({"filament-manager", "filament-manager-worker"})


def _requires_migration(argv: Sequence[str]) -> bool:
    """Return whether this command starts a long-running application service."""

    return bool(argv) and argv[0] in MIGRATING_COMMANDS


def _acquire_migration_lock(connection: Connection, timeout_seconds: int) -> None:
    """Wait a bounded time for the cross-container migration lock."""

    deadline = time.monotonic() + timeout_seconds
    while True:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": MIGRATION_LOCK_KEY},
        )
        if acquired is True:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out after {timeout_seconds} seconds waiting for the database migration lock"
            )
        time.sleep(1)


def upgrade_database(database: DatabaseConfig) -> None:
    """Upgrade through Alembic while holding a PostgreSQL session advisory lock."""

    engine = create_engine(database.resolved_url(), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            _acquire_migration_lock(connection, database.migration_lock_timeout_seconds)
            try:
                logger.info("database_migration_started")
                alembic_config = Config("alembic.ini")
                command.upgrade(alembic_config, "head")
                logger.info("database_migration_completed")
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": MIGRATION_LOCK_KEY},
                )
    finally:
        engine.dispose()


def run() -> None:
    """Run any required migration and replace this process with the requested command."""

    argv = sys.argv[1:]
    if not argv:
        raise SystemExit("No application command was supplied")
    if _requires_migration(argv):
        settings = get_settings()
        configure_logging(settings.app.log_level)
        if settings.database.auto_migrate:
            upgrade_database(settings.database)
        else:
            logger.warning("automatic_database_migration_disabled")
    # Docker supplies this argv directly; execvp preserves normal entry-point
    # override behavior and never invokes a shell.
    os.execvp(argv[0], argv)  # noqa: S606
