"""Sanitized diagnostics and portable text-export tests."""

from datetime import UTC, datetime

from filament_manager.services.diagnostics import (
    EXPECTED_SCHEMA_VERSION,
    _sanitized_error_detail,
    diagnostics_text,
)


def test_expected_schema_matches_current_migration_head() -> None:
    """Diagnostics must advance whenever the single Alembic head advances."""

    assert EXPECTED_SCHEMA_VERSION == "d0e1f2a3b456"


def test_error_details_remove_database_and_external_response_content() -> None:
    """The web view and download never expose SQL or configured external URLs."""

    sql_detail = (
        "(psycopg.errors.UniqueViolation) duplicate key [SQL: INSERT INTO secret_table] "
        "(Background on this error at: https://sqlalche.me/e/20/gkpj)"
    )
    assert _sanitized_error_detail("IntegrityError", sql_detail) == (
        "A database operation failed. Review the server worker log for the matching time."
    )
    assert (
        _sanitized_error_detail(
            "MoonrakerError",
            "Request to http://printer.internal:7125 failed with a sensitive upstream response",
        )
        == "An external integration request failed. Review the server worker log for the matching time."
    )


def test_diagnostics_text_contains_bounded_current_overview() -> None:
    """The text report contains the displayed checks, queue, types, and safe errors."""

    checked_at = datetime(2026, 8, 15, 5, 7, tzinfo=UTC)
    report = diagnostics_text(
        {
            "checked_at": checked_at,
            "checks": [
                {
                    "key": "database.schema",
                    "label": "Canonical PostgreSQL",
                    "category": "connection",
                    "status": "healthy",
                    "detail": "Schema is current at d0e1f2a3b456",
                    "checked_at": checked_at,
                }
            ],
            "queue_counts": {"pending": 3, "dead": 2},
            "job_type_counts": {"moonraker.state.reconcile": 2},
            "error_log": [
                {
                    "source": "Projection worker",
                    "severity": "error",
                    "summary": "moonraker.state.reconcile · RuntimeError",
                    "detail": "Moonraker state synchronization had 2 failures: MoonrakerError x2",
                    "occurred_at": checked_at,
                    "correlation_id": None,
                }
            ],
        }
    )

    assert "Filament Manager diagnostics" in report
    assert "Schema is current at d0e1f2a3b456" in report
    assert "dead: 2" in report
    assert "moonraker.state.reconcile: 2" in report
    assert "MoonrakerError x2" in report
    assert "credentials" in report
