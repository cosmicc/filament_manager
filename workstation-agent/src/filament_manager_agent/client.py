"""Narrow authenticated HTTP client for the workstation agent endpoints."""

import ssl
from typing import Any
from uuid import UUID

import httpx

from .models import AgentConfig, DeploymentClaim


def _http_client(*, timeout: int) -> httpx.Client:
    """Build a strict client using the workstation operating-system trust store.

    HTTPX otherwise selects its bundled Certifi file, which excludes private roots
    installed by an operator in the normal Linux or Windows trust store.  An explicit
    default SSL context preserves hostname and chain verification while honoring those
    system-managed roots and the standard ``SSL_CERT_FILE``/``SSL_CERT_DIR`` overrides.
    """

    return httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        verify=ssl.create_default_context(),
    )


class AgentClient:
    """Server client that never logs or serializes the bearer credential."""

    def __init__(self, config: AgentConfig) -> None:
        self._base_url = str(config.server_url).rstrip("/")
        self._token = config.agent_token.get_secret_value()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def heartbeat(self, payload: dict[str, Any]) -> None:
        with _http_client(timeout=20) as client:
            response = client.post(
                f"{self._base_url}/api/v1/workstation-agent/heartbeat",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()

    def claim(self) -> DeploymentClaim | None:
        with _http_client(timeout=30) as client:
            response = client.post(
                f"{self._base_url}/api/v1/workstation-agent/deployments/claim",
                headers=self._headers(),
            )
            response.raise_for_status()
        data = response.json()
        return DeploymentClaim.model_validate(data) if data is not None else None

    def complete(
        self,
        deployment_id: UUID,
        *,
        outcome: str,
        result: dict[str, Any],
        error_class: str | None = None,
        error_message: str | None = None,
        retry_after_seconds: int = 60,
    ) -> None:
        with _http_client(timeout=30) as client:
            response = client.post(
                f"{self._base_url}/api/v1/workstation-agent/deployments/{deployment_id}/complete",
                headers=self._headers(),
                json={
                    "outcome": outcome,
                    "result": result,
                    "error_class": error_class,
                    "error_message": error_message,
                    "retry_after_seconds": retry_after_seconds,
                },
            )
            response.raise_for_status()


def pair_agent(server_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Exchange a one-time enrollment code without retaining it."""

    with _http_client(timeout=30) as client:
        response = client.post(f"{server_url.rstrip('/')}/api/v1/workstation-agent/pair", json=payload)
        response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("The pairing server returned an invalid response.")
    return value
