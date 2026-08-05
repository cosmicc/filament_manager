"""Async Spoolman REST client using only the supported `/api/v1` contract."""

from typing import Any

import httpx

from filament_manager.config import SpoolmanConfig
from filament_manager.domain.spoolman import merge_extra_fields


class SpoolmanError(RuntimeError):
    """Sanitized Spoolman transport or API failure."""


class SpoolmanClient:
    """Bounded client for health, projection, measurement, and reconciliation."""

    def __init__(self, config: SpoolmanConfig) -> None:
        self.base_url = f"{str(config.base_url).rstrip('/')}/api/v1"
        self.timeout = config.request_timeout_seconds

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, f"{self.base_url}{path}", json=json)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SpoolmanError(f"Spoolman {method} {path} failed") from exc

    async def health(self) -> dict[str, Any]:
        """Return Spoolman's documented health response."""

        data = await self._request("GET", "/health")
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman health returned an invalid payload")
        return data

    async def find_vendors(self, name: str) -> list[dict[str, Any]]:
        """Find exact/near vendor matches by documented query parameter."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/vendor", params={"name": f'"{name}"'})
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SpoolmanError("Spoolman vendor lookup failed") from exc
        if not isinstance(data, list):
            raise SpoolmanError("Spoolman vendor lookup returned an invalid payload")
        return data

    async def create_vendor(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/vendor", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman vendor creation returned an invalid payload")
        return data

    async def get_vendor(self, vendor_id: int) -> dict[str, Any]:
        data = await self._request("GET", f"/vendor/{vendor_id}")
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman vendor returned an invalid payload")
        return data

    async def update_vendor(self, vendor_id: int, managed_payload: dict[str, Any]) -> dict[str, Any]:
        remote = await self.get_vendor(vendor_id)
        payload = dict(managed_payload)
        payload["extra"] = merge_extra_fields(remote.get("extra"), payload.get("extra", {}))
        data = await self._request("PATCH", f"/vendor/{vendor_id}", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman vendor update returned an invalid payload")
        return data

    async def create_filament(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/filament", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman filament creation returned an invalid payload")
        return data

    async def get_filament(self, filament_id: int) -> dict[str, Any]:
        data = await self._request("GET", f"/filament/{filament_id}")
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman filament returned an invalid payload")
        return data

    async def update_filament(self, filament_id: int, managed_payload: dict[str, Any]) -> dict[str, Any]:
        remote = await self.get_filament(filament_id)
        payload = dict(managed_payload)
        payload["extra"] = merge_extra_fields(remote.get("extra"), payload.get("extra", {}))
        data = await self._request("PATCH", f"/filament/{filament_id}", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman filament update returned an invalid payload")
        return data

    async def create_spool(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/spool", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman spool creation returned an invalid payload")
        return data

    async def get_spool(self, spool_id: int) -> dict[str, Any]:
        data = await self._request("GET", f"/spool/{spool_id}")
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman spool returned an invalid payload")
        return data

    async def update_spool(self, spool_id: int, managed_payload: dict[str, Any]) -> dict[str, Any]:
        remote = await self.get_spool(spool_id)
        payload = dict(managed_payload)
        payload["extra"] = merge_extra_fields(remote.get("extra"), payload.get("extra", {}))
        data = await self._request("PATCH", f"/spool/{spool_id}", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman spool update returned an invalid payload")
        return data

    async def measure_spool(self, spool_id: int, gross_weight_g: float) -> dict[str, Any]:
        """Submit the documented current gross-weight measurement."""

        data = await self._request("PUT", f"/spool/{spool_id}/measure", json={"weight": gross_weight_g})
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman measurement returned an invalid payload")
        return data

    async def list_spools(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/spool")
        if not isinstance(data, list):
            raise SpoolmanError("Spoolman spool list returned an invalid payload")
        return data
