"""Supported Moonraker HTTP client for active spool and plate selection."""

from typing import Any

import httpx

from filament_manager.config import PrinterConfig


class MoonrakerError(RuntimeError):
    """Sanitized Moonraker transport or API failure."""


class MoonrakerClient:
    """Client constrained to a configured printer endpoint."""

    def __init__(self, printer: PrinterConfig, timeout: float = 10) -> None:
        self.base_url = str(printer.base_url).rstrip("/")
        self.timeout = timeout
        self.api_key = printer.resolved_api_key()

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key} if self.api_key else {}

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
                response = await client.post(f"{self.base_url}{path}", json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MoonrakerError(f"Moonraker POST {path} failed") from exc
        if not isinstance(data, dict):
            raise MoonrakerError("Moonraker returned an invalid payload")
        return data

    async def health(self) -> dict[str, Any]:
        """Read Moonraker server information as a liveness check."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
                response = await client.get(f"{self.base_url}/server/info")
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MoonrakerError("Moonraker health check failed") from exc
        if not isinstance(data, dict):
            raise MoonrakerError("Moonraker health returned an invalid payload")
        return data

    async def set_active_spool(self, spoolman_id: int | None) -> dict[str, Any]:
        """Use Moonraker's supported active-spool integration endpoint."""

        return await self._post("/server/spoolman/spool_id", {"spool_id": spoolman_id})

    async def select_build_plate(self, plate_code: str) -> dict[str, Any]:
        """Call the documented integration macro without editing printer files."""

        if plate_code not in {"P1", "P2", "P3", "P4", "P5"}:
            raise ValueError("plate code must be P1 through P5")
        return await self._post("/printer/gcode/script", {"script": f"SELECT_BUILD_PLATE PLATE={plate_code}"})
