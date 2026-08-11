"""Tests for the container readiness probe."""

from __future__ import annotations

from types import TracebackType
from urllib.request import Request

import pytest

from filament_manager import healthcheck


class _SuccessfulResponse:
    """Minimal context-managed response returned by the probe test double."""

    def __enter__(self) -> _SuccessfulResponse:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> bytes:
        """Return a successful readiness payload."""

        return b'{"status":"ready"}'


def test_readiness_probe_uses_public_hostname_on_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trusted-host validation sees the configured public host, not loopback."""

    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, *, timeout: int) -> _SuccessfulResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _SuccessfulResponse()

    monkeypatch.setenv("FILAMENT_MANAGER_BASE_URL", "https://filament.example.test:8443/app")
    monkeypatch.setattr(healthcheck, "urlopen", fake_urlopen)

    healthcheck.check_readiness()

    request = captured["request"]
    assert isinstance(request, Request)
    assert request.full_url == healthcheck.READINESS_URL
    assert request.get_header("Host") == "filament.example.test"
    assert captured["timeout"] == healthcheck.HEALTHCHECK_TIMEOUT_SECONDS


def test_readiness_probe_rejects_base_url_without_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid deployment URL must fail closed instead of weakening host checks."""

    monkeypatch.setenv("FILAMENT_MANAGER_BASE_URL", "not-a-url")

    with pytest.raises(RuntimeError, match="must contain a hostname"):
        healthcheck.configured_public_hostname()
