"""Privacy-hardened Bugsnag reporting for web and worker service boundaries."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import bugsnag
import structlog

from filament_manager import __version__
from filament_manager.config import BugsnagConfig

logger = structlog.get_logger()

type TelemetryScalar = str | int | float | bool | None
type TelemetryMetadata = Mapping[str, TelemetryScalar]
type TelemetrySeverity = Literal["error", "warning", "info"]

_SAFE_CONTEXT_PATTERN = re.compile(r"[^A-Za-z0-9 ./_:{\}-]+")
_SAFE_VALUE_PATTERN = re.compile(r"[^A-Za-z0-9 ._:/@{\}-]+")
_SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "cookie",
    "csrf",
    "database",
    "password",
    "secret",
    "service_account",
    "session",
    "token",
    "url",
)


def _bounded_safe_text(value: object, *, limit: int = 160) -> str:
    """Return bounded identifier-style telemetry text without raw punctuation."""

    return _SAFE_VALUE_PATTERN.sub("_", str(value))[:limit]


def _safe_metadata(metadata: TelemetryMetadata | None) -> dict[str, TelemetryScalar]:
    """Allow only flat, bounded, explicitly supplied non-sensitive metadata."""

    sanitized: dict[str, TelemetryScalar] = {}
    for raw_key, raw_value in (metadata or {}).items():
        key = _bounded_safe_text(raw_key, limit=64).lower()
        if not key or any(fragment in key for fragment in _SENSITIVE_KEY_FRAGMENTS):
            continue
        if isinstance(raw_value, str):
            sanitized[key] = _bounded_safe_text(raw_value)
        elif raw_value is None or isinstance(raw_value, (bool, int, float)):
            sanitized[key] = raw_value
    return sanitized


def _sanitized_stack_file(value: object) -> str:
    """Remove absolute host paths while retaining useful package-relative frames."""

    normalized = str(value).replace("\\", "/")
    marker = "/filament_manager/"
    if marker in normalized:
        return f"filament_manager/{normalized.split(marker, 1)[1]}"[:300]
    return Path(normalized).name[:160] or "unknown"


def _sanitize_event(event: Any) -> None:
    """Strip messages and host-local data immediately before Bugsnag delivery."""

    for error in event.errors:
        error.error_message = (
            "A sanitized application error occurred; use the attached local correlation data."
        )
        for frame in error.stacktrace:
            frame["file"] = _sanitized_stack_file(frame.get("file", "unknown"))
            frame.pop("code", None)
    event.hostname = "self-hosted"
    event.user = {}
    event.request = None
    event.session = None
    event.context = _SAFE_CONTEXT_PATTERN.sub("_", str(event.context or "application"))[:160]
    event.metadata = {"filament_manager": _safe_metadata(event.metadata.get("filament_manager", {}))}


class ServerTelemetry:
    """Small fail-safe notifier with bounded duplicate suppression."""

    def __init__(self, config: BugsnagConfig, *, app_type: Literal["web", "worker"]) -> None:
        """Create an isolated notifier client when the integration is enabled."""

        self._client: Any | None = None
        self._last_reported: dict[str, float] = {}
        self._lock = threading.Lock()
        if not config.enabled:
            return
        api_key = config.resolved_api_key()
        if api_key is None:  # The validated model prevents this defensive branch.
            return
        self._client = bugsnag.Client(
            api_key=api_key,
            app_type=f"filament-manager-{app_type}",
            app_version=__version__,
            release_stage=config.release_stage,
            notify_release_stages=[config.release_stage],
            asynchronous=True,
            auto_notify=False,
            auto_capture_sessions=False,
            enabled_breadcrumb_types=[],
            hostname="self-hosted",
            install_sys_hook=False,
            max_breadcrumbs=0,
            params_filters=list(_SENSITIVE_KEY_FRAGMENTS),
            project_root=str(Path(__file__).resolve().parent),
            send_code=False,
            send_environment=False,
        )
        # bugsnag-python's callback annotation incorrectly requires another callable return value.
        self._client.configuration.middleware.before_notify(_sanitize_event)  # type: ignore[arg-type]

    @property
    def enabled(self) -> bool:
        """Return whether a configured notifier client is available."""

        return self._client is not None

    def notify(
        self,
        error: BaseException,
        *,
        context: str,
        metadata: TelemetryMetadata | None = None,
        severity: TelemetrySeverity = "error",
        throttle_seconds: float = 0,
        synchronous: bool = False,
    ) -> bool:
        """Send one sanitized event without affecting application control flow."""

        if self._client is None:
            return False
        safe_context = _SAFE_CONTEXT_PATTERN.sub("_", context)[:160]
        throttle_key = f"{safe_context}:{type(error).__module__}.{type(error).__qualname__}"
        if throttle_seconds > 0:
            now = time.monotonic()
            with self._lock:
                last_reported = self._last_reported.get(throttle_key)
                if last_reported is not None and now - last_reported < throttle_seconds:
                    return False
                self._last_reported[throttle_key] = now
        try:
            self._client.notify(
                error,
                asynchronous=not synchronous,
                context=safe_context,
                metadata={"filament_manager": _safe_metadata(metadata)},
                severity=severity,
                traceback=error.__traceback__,
                user={},
            )
        except Exception as delivery_error:
            logger.warning(
                "bugsnag_notification_failed",
                app_type=self._client.configuration.app_type,
                error_class=type(delivery_error).__name__,
            )
            return False
        return True
