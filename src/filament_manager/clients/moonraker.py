"""Supported Moonraker HTTP client for spool, plate, and bed-mesh operations."""

from dataclasses import dataclass
from typing import Any

import httpx

from filament_manager.config import PrinterConfig
from filament_manager.domain.build_plates import is_build_plate_surface_code


class MoonrakerError(RuntimeError):
    """Sanitized Moonraker transport or API failure."""


@dataclass(frozen=True, slots=True)
class MoonrakerBedMeshState:
    """Saved bed-mesh profile names and the currently loaded profile."""

    profile_names: tuple[str, ...]
    active_profile: str | None


@dataclass(frozen=True, slots=True)
class MoonrakerPrinterInformation:
    """Documented Moonraker and Klipper fields used for canonical metadata."""

    server_info: dict[str, Any]
    printer_info: dict[str, Any]
    object_status: dict[str, Any]


class MoonrakerClient:
    """Client constrained to a configured printer endpoint."""

    def __init__(self, printer: PrinterConfig, timeout: float = 10) -> None:
        self.base_url = str(printer.base_url).rstrip("/")
        self.timeout = timeout
        self.api_key = printer.resolved_api_key()

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key} if self.api_key else {}

    async def _get(self, path: str) -> dict[str, Any]:
        """Perform one authenticated GET and reject malformed API envelopes."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
                response = await client.get(f"{self.base_url}{path}")
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MoonrakerError(f"Moonraker GET {path} failed") from exc
        if not isinstance(data, dict) or "error" in data:
            raise MoonrakerError(f"Moonraker GET {path} returned an invalid payload")
        return data

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
        if "error" in data:
            raise MoonrakerError(f"Moonraker POST {path} returned an API error")
        return data

    async def health(self) -> dict[str, Any]:
        """Read Moonraker server information as a liveness check."""

        return await self._get("/server/info")

    async def printer_information(self) -> MoonrakerPrinterInformation:
        """Read only documented, useful printer identity and configuration fields."""

        server_payload = await self._get("/server/info")
        printer_payload = await self._get("/printer/info")
        object_payload = await self._post(
            "/printer/objects/query",
            {
                "objects": {
                    "configfile": ["settings"],
                    "toolhead": ["axis_minimum", "axis_maximum", "cone_start_z"],
                }
            },
        )
        server_info = server_payload.get("result")
        printer_info = printer_payload.get("result")
        object_result = object_payload.get("result")
        object_status = object_result.get("status") if isinstance(object_result, dict) else None
        if (
            not isinstance(server_info, dict)
            or not isinstance(printer_info, dict)
            or not isinstance(object_status, dict)
        ):
            raise MoonrakerError("Moonraker printer information was incomplete")
        return MoonrakerPrinterInformation(
            server_info=server_info,
            printer_info=printer_info,
            object_status=object_status,
        )

    async def set_active_spool(self, spoolman_id: int | None) -> dict[str, Any]:
        """Use Moonraker's supported active-spool integration endpoint."""

        return await self._post("/server/spoolman/spool_id", {"spool_id": spoolman_id})

    async def active_spool_id(self) -> int | None:
        """Read the Spoolman ID Moonraker currently tracks for filament usage."""

        payload = await self._get("/server/spoolman/spool_id")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise MoonrakerError("Moonraker active-spool query returned an invalid result")
        spool_id = result.get("spool_id")
        if spool_id is None:
            return None
        if isinstance(spool_id, bool) or not isinstance(spool_id, int) or spool_id <= 0:
            raise MoonrakerError("Moonraker returned an invalid active spool ID")
        return int(spool_id)

    async def bed_mesh_state(self) -> MoonrakerBedMeshState:
        """Read saved bed meshes and the loaded mesh through printer object status."""

        payload = await self._post(
            "/printer/objects/query",
            {"objects": {"bed_mesh": ["profile_name", "profiles"]}},
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise MoonrakerError("Moonraker bed-mesh query returned an invalid result")
        status = result.get("status")
        bed_mesh = status.get("bed_mesh") if isinstance(status, dict) else None
        if not isinstance(bed_mesh, dict):
            raise MoonrakerError("Moonraker did not return the bed_mesh printer object")
        profiles = bed_mesh.get("profiles")
        active_profile = bed_mesh.get("profile_name")
        if not isinstance(profiles, dict) or not all(isinstance(name, str) for name in profiles):
            raise MoonrakerError("Moonraker returned invalid bed-mesh profiles")
        if not isinstance(active_profile, str):
            raise MoonrakerError("Moonraker returned an invalid active bed-mesh profile")
        return MoonrakerBedMeshState(
            profile_names=tuple(profiles),
            active_profile=active_profile or None,
        )

    async def select_build_plate(self, plate_code: str) -> dict[str, Any]:
        """Call the documented integration macro without editing printer files."""

        if not is_build_plate_surface_code(plate_code):
            raise ValueError("plate side must use the exact P<number> or P<number>b format")
        return await self._post("/printer/gcode/script", {"script": f"SELECT_BUILD_PLATE PLATE={plate_code}"})
