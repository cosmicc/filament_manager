"""Privacy and failure-isolation tests for optional Bugsnag reporting."""

from types import SimpleNamespace
from typing import Any

import pytest
from bugsnag.configuration import Configuration, RequestConfiguration
from bugsnag.event import Event
from pydantic import ValidationError

from filament_manager.config import BugsnagConfig, Settings
from filament_manager.main import _browser_runtime_config, _content_security_policy
from filament_manager.telemetry import ServerTelemetry, _sanitize_event

BUGSNAG_API_KEY = "a" * 32


def test_bugsnag_configuration_is_opt_in_and_requires_a_valid_key() -> None:
    """Disabled installations stay local and enabled installations fail closed."""

    assert BugsnagConfig().enabled is False
    with pytest.raises(ValidationError, match="requires an API key"):
        BugsnagConfig(enabled=True)
    with pytest.raises(ValidationError, match="32 hexadecimal"):
        BugsnagConfig(enabled=True, api_key="not-a-key")
    with pytest.raises(ValidationError, match="browser performance requires"):
        BugsnagConfig(browser_performance_enabled=True)


def test_runtime_browser_config_and_csp_expose_only_required_public_values() -> None:
    """The browser key is served only when enabled and CSP opens exact ingest hosts."""

    disabled = Settings.model_construct(bugsnag=BugsnagConfig())
    assert _browser_runtime_config(disabled) == {
        "bugsnag": {
            "enabled": False,
            "apiKey": None,
            "releaseStage": "production",
            "browserPerformanceEnabled": False,
        }
    }
    assert "bugsnag.com" not in _content_security_policy(disabled)

    enabled = Settings.model_construct(
        bugsnag=BugsnagConfig(
            enabled=True,
            api_key=BUGSNAG_API_KEY,
            release_stage="testing",
            browser_performance_enabled=True,
        )
    )
    runtime_config = _browser_runtime_config(enabled)
    assert runtime_config["bugsnag"] == {
        "enabled": True,
        "apiKey": BUGSNAG_API_KEY,
        "releaseStage": "testing",
        "browserPerformanceEnabled": True,
    }
    policy = _content_security_policy(enabled)
    assert "https://notify.bugsnag.com" in policy
    assert "https://sessions.bugsnag.com" not in policy
    assert f"https://{BUGSNAG_API_KEY}.otlp.bugsnag.com" in policy
    assert "*.bugsnag.com" not in policy


def test_python_event_sanitizer_removes_messages_paths_and_sensitive_metadata() -> None:
    """No raw exception text, absolute path, hostname, user, or arbitrary tab is delivered."""

    config = Configuration()
    config.configure(api_key=BUGSNAG_API_KEY, project_root="/private/project")
    try:
        raise RuntimeError("postgresql://user:password@private.example/database?token=secret")
    except RuntimeError as error:
        event = Event(
            error,
            config,
            RequestConfiguration(),
            context="GET /spools/private?token=secret",
            metadata={
                "filament_manager": {
                    "correlation_id": "safe-id",
                    "database_url": "postgresql://private",
                    "job_type": "spoolman.reconcile.full",
                },
                "request": {"password": "secret"},
            },
            user={"id": "admin"},
        )

    _sanitize_event(event)

    assert event.errors[0].error_message.startswith("A sanitized application error")
    assert all(not frame["file"].startswith("/") for frame in event.errors[0].stacktrace)
    assert event.hostname == "self-hosted"
    assert event.user == {}
    assert event.context == "GET /spools/private_token_secret"
    assert event.metadata == {
        "filament_manager": {
            "correlation_id": "safe-id",
            "job_type": "spoolman.reconcile.full",
        }
    }


def test_server_reporter_throttles_duplicate_worker_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repeating worker failure cannot consume one Bugsnag event per retry loop."""

    callbacks: list[Any] = []
    notifications: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, **options: Any) -> None:
            self.configuration = SimpleNamespace(
                app_type=options["app_type"],
                middleware=SimpleNamespace(before_notify=callbacks.append),
            )

        def notify(self, error: BaseException, **options: Any) -> None:
            notifications.append({"error": error, **options})

    monkeypatch.setattr("filament_manager.telemetry.bugsnag.Client", FakeClient)
    reporter = ServerTelemetry(
        BugsnagConfig(enabled=True, api_key=BUGSNAG_API_KEY),
        app_type="worker",
    )
    error = RuntimeError("private upstream response")

    assert reporter.notify(error, context="worker.scheduler", throttle_seconds=300)
    assert not reporter.notify(error, context="worker.scheduler", throttle_seconds=300)
    assert len(callbacks) == 1
    assert len(notifications) == 1
    assert notifications[0]["metadata"] == {"filament_manager": {}}
