"""Automatic database migration entry-point tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from filament_manager import startup


@pytest.mark.parametrize("command", ["filament-manager", "filament-manager-worker"])
def test_long_running_commands_require_migrations(command: str) -> None:
    assert startup._requires_migration([command]) is True


@pytest.mark.parametrize("command", ["filament-manager-cli", "alembic", "python"])
def test_one_shot_commands_do_not_implicitly_migrate(command: str) -> None:
    assert startup._requires_migration([command]) is False


def test_upgrade_holds_lock_while_alembic_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    connection = Mock()
    connection.scalar.return_value = True

    @contextmanager
    def connect() -> Iterator[Mock]:
        events.append("connected")
        yield connection
        events.append("disconnected")

    engine = Mock()
    engine.connect.side_effect = connect
    monkeypatch.setattr(startup, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(startup.command, "upgrade", lambda _config, _target: events.append("upgraded"))

    database = Mock()
    database.resolved_url.return_value = "postgresql+psycopg://redacted"
    database.migration_lock_timeout_seconds = 30
    startup.upgrade_database(database)

    assert events == ["connected", "upgraded", "disconnected"]
    assert connection.scalar.call_count == 1
    assert connection.execute.call_count == 1
    engine.dispose.assert_called_once_with()


def test_migration_lock_wait_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Mock()
    connection.scalar.return_value = False
    monotonic_values = iter([0.0, 11.0])
    monkeypatch.setattr(startup.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(startup.time, "sleep", Mock())

    with pytest.raises(TimeoutError, match="Timed out after 10 seconds"):
        startup._acquire_migration_lock(connection, 10)
