"""Sanitized diagnostics and portable text-export tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

from filament_manager.services.diagnostics import (
    EXPECTED_SCHEMA_VERSION,
    _cura_material_settings_check,
    _sanitized_error_detail,
    diagnostics_text,
)


def test_expected_schema_matches_current_migration_head() -> None:
    """Diagnostics must advance whenever the single Alembic head advances."""

    assert EXPECTED_SCHEMA_VERSION == "b0c1d2e3f456"


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


def test_cura_material_setting_receipts_report_exact_health_and_safe_drift() -> None:
    """Diagnostics distinguishes verified exposure from bounded setting drift."""

    checked_at = datetime(2026, 8, 22, 4, 0, tzinfo=UTC)
    agent = SimpleNamespace(
        id="agent-id",
        display_name="Workshop Cura",
        enabled=True,
        cura_management_enabled=True,
    )
    healthy = _cura_material_settings_check(
        agent,
        {
            "installation_id": "cura-513",
            "version": "5.13",
            "material_settings_sync": {
                "status": "healthy",
                "expected_count": 54,
                "exposed_count": 54,
                "missing_keys": [],
                "material_settings_plugin_ready": True,
                "klipper_settings_plugin_ready": True,
            },
        },
        checked_at,
    )
    degraded = _cura_material_settings_check(
        agent,
        {
            "installation_id": "cura-513",
            "version": "5.13",
            "material_settings_sync": {
                "status": "degraded",
                "expected_count": 54,
                "exposed_count": 54,
                "missing_keys": ["speed_print", "not_a_managed_key"],
                "material_settings_plugin_ready": True,
                "klipper_settings_plugin_ready": False,
            },
        },
        checked_at,
    )

    assert healthy["status"] == "healthy"
    assert "54 of 54" in str(healthy["detail"])
    assert degraded["status"] == "error"
    assert "speed_print" in str(degraded["detail"])
    assert "not_a_managed_key" not in str(degraded["detail"])


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
                    "detail": "Schema is current at e1f2a3b4c567",
                    "checked_at": checked_at,
                }
            ],
            "queue_counts": {"pending": 3, "dead": 2},
            "job_type_counts": {"moonraker.state.reconcile": 2},
            "failure_groups": [
                {
                    "job_type": "spoolman.spool.adjust_weight",
                    "count": 2,
                    "status": "dead",
                    "attempts": 12,
                    "max_attempts": 12,
                    "error_class": "SpoolmanError",
                    "detail": "Spoolman PUT /spool/7/measure failed",
                    "occurred_at": checked_at,
                }
            ],
            "error_log": [
                {
                    "source": "Projection worker",
                    "severity": "error",
                    "summary": "moonraker.state.reconcile · RuntimeError",
                    "detail": "Moonraker state synchronization had 2 failures: MoonrakerError x2",
                    "occurred_at": checked_at,
                    "correlation_id": None,
                    "current": False,
                }
            ],
        }
    )

    assert "Filament Manager diagnostics" in report
    assert "Schema is current at e1f2a3b4c567" in report
    assert "dead: 2" in report
    assert "moonraker.state.reconcile: 2" in report
    assert "spoolman.spool.adjust_weight: 2 actionable failure(s)" in report
    assert "Spoolman PUT /spool/7/measure failed" in report
    assert "[HISTORY ERROR]" in report
    assert "MoonrakerError x2" in report
    assert "credentials" in report
