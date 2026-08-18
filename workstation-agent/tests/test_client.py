"""Secure workstation-agent HTTP client tests."""

import ssl

import pytest

from filament_manager_agent import client as client_module


def test_http_client_uses_operating_system_tls_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Private roots in the OS store remain trusted without disabling verification."""

    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    captured: dict[str, object] = {}

    def fake_client(**options: object) -> object:
        captured.update(options)
        return object()

    monkeypatch.setattr(client_module.ssl, "create_default_context", lambda: tls_context)
    monkeypatch.setattr(client_module.httpx, "Client", fake_client)

    result = client_module._http_client(timeout=20)

    assert result is not None
    assert captured == {
        "timeout": 20,
        "follow_redirects": False,
        "verify": tls_context,
    }
    assert tls_context.verify_mode == ssl.CERT_REQUIRED
    assert tls_context.check_hostname is True
