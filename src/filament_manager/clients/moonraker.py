"""Supported Moonraker HTTP client for spool, plate, and bed-mesh operations."""

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx

from filament_manager.config import PrinterConfig
from filament_manager.domain.build_plates import is_build_plate_surface_code
from filament_manager.domain.spool_preflight import (
    SpoolPreflightCatalog,
    validate_catalog_revision,
)


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


@dataclass(frozen=True, slots=True)
class MoonrakerSpoolPreflightState:
    """Persistent physical-spool state reported by the Klipper macro."""

    restored: bool
    initialized: bool
    phase: str
    loaded_spool_id: int | None
    catalog_revision: str
    material_guid: str
    start_bed_temp: Decimal
    start_extruder_temp: Decimal
    start_chamber_temp: Decimal
    inspection_policy: str
    start_pending: bool


@dataclass(frozen=True, slots=True)
class MoonrakerPrintState:
    """Current documented print_stats state needed for live history capture."""

    filename: str
    state: str
    message: str | None
    total_duration: Decimal
    print_duration: Decimal
    filament_used_mm: Decimal


@dataclass(frozen=True, slots=True)
class MoonrakerGcodeFile:
    """Streaming G-code digest plus bounded header and tail samples."""

    sha256: str
    header: str
    tail: str
    size: int


SPOOL_PROMPT_LABEL_PATTERN = re.compile(r"[A-Za-z0-9._#-]{1,96}")
SPOOL_PREFLIGHT_PHASES = {
    "idle",
    "selecting",
    "unloading",
    "inserting",
    "loading",
    "ready",
    "manual_select",
    "manual_ready",
    "load_select",
    "spoolman_select",
    "error",
    "inspecting",
}


class MoonrakerClient:
    """Client constrained to a configured printer endpoint."""

    def __init__(self, printer: PrinterConfig, timeout: float = 10) -> None:
        self.base_url = str(printer.base_url).rstrip("/")
        self.timeout = timeout
        self.api_key = printer.resolved_api_key()

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key} if self.api_key else {}

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str | int | float | bool | None] | None = None,
    ) -> dict[str, Any]:
        """Perform one authenticated GET and reject malformed API envelopes."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
                response = await client.get(f"{self.base_url}{path}", params=params)
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

    async def spool_preflight_state(self) -> MoonrakerSpoolPreflightState | None:
        """Read the app-owned macro state without treating a missing install as fatal."""

        payload = await self._post(
            "/printer/objects/query",
            {
                "objects": {
                    "gcode_macro FILAMENT_MANAGER_SPOOL_STATE": [
                        "restored",
                        "initialized",
                        "phase",
                        "loaded_spool_id",
                        "catalog_revision",
                        "material_guid",
                        "start_bed_temp",
                        "start_extruder_temp",
                        "start_chamber_temp",
                        "inspection_policy",
                        "start_pending",
                    ]
                }
            },
        )
        result = payload.get("result")
        status = result.get("status") if isinstance(result, dict) else None
        macro_state = (
            status.get("gcode_macro FILAMENT_MANAGER_SPOOL_STATE") if isinstance(status, dict) else None
        )
        if macro_state is None:
            return None
        if not isinstance(macro_state, dict):
            raise MoonrakerError("Moonraker returned invalid spool-preflight macro state")
        restored = macro_state.get("restored")
        initialized = macro_state.get("initialized")
        phase = macro_state.get("phase")
        loaded_spool_id = macro_state.get("loaded_spool_id")
        revision = macro_state.get("catalog_revision")
        material_guid = macro_state.get("material_guid", "")
        start_bed_temp = macro_state.get("start_bed_temp", 0)
        start_extruder_temp = macro_state.get("start_extruder_temp", 0)
        start_chamber_temp = macro_state.get("start_chamber_temp", 0)
        inspection_policy = macro_state.get("inspection_policy", "warn")
        start_pending = macro_state.get("start_pending", 0)
        if restored not in (0, 1, False, True):
            raise MoonrakerError("Moonraker returned an invalid spool-preflight restored flag")
        if initialized not in (0, 1, False, True):
            raise MoonrakerError("Moonraker returned an invalid spool-preflight initialized flag")
        if not isinstance(phase, str) or phase not in SPOOL_PREFLIGHT_PHASES:
            raise MoonrakerError("Moonraker returned an invalid spool-preflight phase")
        if isinstance(loaded_spool_id, bool) or not isinstance(loaded_spool_id, int):
            raise MoonrakerError("Moonraker returned an invalid physically loaded spool ID")
        if loaded_spool_id == 0 or loaded_spool_id < -1:
            raise MoonrakerError("Moonraker returned an invalid physically loaded spool ID")
        if not isinstance(revision, str):
            raise MoonrakerError("Moonraker returned an invalid spool catalog revision")
        if not isinstance(material_guid, str) or len(material_guid) > 96:
            raise MoonrakerError("Moonraker returned an invalid managed material GUID")
        try:
            temperatures = tuple(
                Decimal(str(value)) for value in (start_bed_temp, start_extruder_temp, start_chamber_temp)
            )
        except Exception as exc:
            raise MoonrakerError("Moonraker returned invalid print-start temperatures") from exc
        if any(not value.is_finite() or value < 0 or value > 500 for value in temperatures):
            raise MoonrakerError("Moonraker returned invalid print-start temperatures")
        if inspection_policy not in {"warn", "block"}:
            raise MoonrakerError("Moonraker returned an invalid G-code inspection policy")
        if not isinstance(start_pending, (bool, int)) or int(start_pending) not in {0, 1}:
            raise MoonrakerError("Moonraker returned an invalid print-start pending state")
        if revision:
            try:
                validate_catalog_revision(revision)
            except ValueError as exc:
                raise MoonrakerError("Moonraker returned an invalid spool catalog revision") from exc
        return MoonrakerSpoolPreflightState(
            restored=bool(restored),
            initialized=bool(initialized),
            phase=phase,
            loaded_spool_id=loaded_spool_id if loaded_spool_id > 0 else None,
            catalog_revision=revision,
            material_guid=material_guid,
            start_bed_temp=temperatures[0],
            start_extruder_temp=temperatures[1],
            start_chamber_temp=temperatures[2],
            inspection_policy=inspection_policy,
            start_pending=bool(start_pending),
        )

    async def print_state(self) -> MoonrakerPrintState:
        """Read the current documented print_stats fields."""

        payload = await self._post(
            "/printer/objects/query",
            {
                "objects": {
                    "print_stats": [
                        "filename",
                        "state",
                        "message",
                        "total_duration",
                        "print_duration",
                        "filament_used",
                    ]
                }
            },
        )
        result = payload.get("result")
        status = result.get("status") if isinstance(result, dict) else None
        stats = status.get("print_stats") if isinstance(status, dict) else None
        if not isinstance(stats, dict):
            raise MoonrakerError("Moonraker did not return print_stats")
        filename = stats.get("filename")
        state = stats.get("state")
        message = stats.get("message")
        if not isinstance(filename, str) or len(filename) > 512:
            raise MoonrakerError("Moonraker returned an invalid print filename")
        if state not in {"standby", "printing", "paused", "error", "complete", "cancelled"}:
            raise MoonrakerError("Moonraker returned an invalid print state")
        if message is not None and not isinstance(message, str):
            raise MoonrakerError("Moonraker returned an invalid print message")
        try:
            durations = tuple(
                Decimal(str(stats.get(key, 0)))
                for key in ("total_duration", "print_duration", "filament_used")
            )
        except Exception as exc:
            raise MoonrakerError("Moonraker returned invalid print counters") from exc
        if any(not value.is_finite() or value < 0 for value in durations):
            raise MoonrakerError("Moonraker returned invalid print counters")
        return MoonrakerPrintState(
            filename=filename,
            state=state,
            message=message[:500] if message else None,
            total_duration=durations[0],
            print_duration=durations[1],
            filament_used_mm=durations[2],
        )

    async def history_jobs(
        self, *, start: int = 0, limit: int = 100, since: float | None = None
    ) -> tuple[dict[str, Any], ...]:
        """Return one bounded page from Moonraker's supported history component."""

        if start < 0 or limit < 1 or limit > 200:
            raise ValueError("invalid Moonraker history page")
        params: dict[str, str | int | float | bool | None] = {
            "start": start,
            "limit": limit,
            "order": "asc",
        }
        if since is not None:
            params["since"] = since
        payload = await self._get("/server/history/list", params=params)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise MoonrakerError("Moonraker returned an invalid history result")
        jobs = result.get("jobs")
        if not isinstance(jobs, list) or len(jobs) > limit or not all(isinstance(job, dict) for job in jobs):
            raise MoonrakerError("Moonraker returned invalid history jobs")
        return tuple(jobs)

    @staticmethod
    def _validated_gcode_filename(filename: str) -> str:
        """Reject control characters, absolute paths, and traversal before a download."""

        if not filename or len(filename) > 512 or filename.startswith(("/", "\\")):
            raise ValueError("invalid G-code filename")
        if any(ord(character) < 32 for character in filename):
            raise ValueError("invalid G-code filename")
        parts = filename.replace("\\", "/").split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("invalid G-code filename")
        return "/".join(parts)

    async def gcode_metadata(self, filename: str) -> dict[str, Any]:
        """Read Moonraker's supported per-file metadata envelope."""

        validated = self._validated_gcode_filename(filename)
        payload = await self._get("/server/files/metadata", params={"filename": validated})
        result = payload.get("result")
        if not isinstance(result, dict):
            raise MoonrakerError("Moonraker returned invalid G-code metadata")
        return result

    async def gcode_file(
        self,
        filename: str,
        *,
        sample_bytes: int = 524_288,
        max_bytes: int = 1_000_000_000,
    ) -> MoonrakerGcodeFile:
        """Stream one G-code file once while hashing and retaining bounded samples."""

        validated = self._validated_gcode_filename(filename)
        if sample_bytes < 1 or sample_bytes > 1_100_000 or max_bytes < sample_bytes:
            raise ValueError("invalid G-code download bounds")
        encoded = quote(validated, safe="/")
        digest = hashlib.sha256()
        header = bytearray()
        tail = bytearray()
        size = 0
        try:
            async with httpx.AsyncClient(timeout=max(self.timeout, 60), headers=self._headers()) as client:
                async with client.stream("GET", f"{self.base_url}/server/files/gcodes/{encoded}") as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise MoonrakerError("G-code file exceeds the inspection size limit")
                        digest.update(chunk)
                        if len(header) < sample_bytes:
                            header.extend(chunk[: sample_bytes - len(header)])
                        tail.extend(chunk)
                        if len(tail) > sample_bytes:
                            del tail[: len(tail) - sample_bytes]
        except MoonrakerError:
            raise
        except httpx.HTTPError as exc:
            raise MoonrakerError("Moonraker G-code download failed") from exc
        return MoonrakerGcodeFile(
            sha256=digest.hexdigest(),
            header=header.decode("utf-8", errors="replace"),
            tail=tail.decode("utf-8", errors="replace"),
            size=size,
        )

    async def submit_gcode_inspection(self, *, passed: bool) -> dict[str, Any]:
        """Release or retain a print paused by the managed blocking gate."""

        return await self._post(
            "/printer/gcode/script",
            {"script": f"FILAMENT_MANAGER_GCODE_INSPECTION PASS={1 if passed else 0}"},
        )

    async def request_spool_unload(self) -> dict[str, Any]:
        """Start the guarded physical unload workflow without selecting a replacement."""

        return await self._post("/printer/gcode/script", {"script": "FILAMENT_MANAGER_UNLOAD_SPOOL"})

    async def clear_build_plate(self) -> dict[str, Any]:
        """Clear the loaded mesh so state reconciliation can clear active plate context."""

        return await self._post("/printer/gcode/script", {"script": "FILAMENT_MANAGER_CLEAR_BUILD_PLATE"})

    async def synchronize_spool_preflight_catalog(
        self, catalog: SpoolPreflightCatalog, *, inspection_policy: str = "warn"
    ) -> dict[str, Any]:
        """Persist a bounded catalog for offline-safe Fluidd macro prompts."""

        if inspection_policy not in {"warn", "block"}:
            raise ValueError("unsupported G-code inspection policy")
        revision = validate_catalog_revision(catalog.revision)
        materials = catalog.materials_literal()
        manual_spools = catalog.manual_spools_literal()
        print_temperatures = catalog.print_temperatures_literal()
        temperatures = catalog.temperatures_literal()
        script = "\n".join(
            (
                f"SET_GCODE_VARIABLE MACRO=FILAMENT_MANAGER_SPOOL_STATE VARIABLE=catalog VALUE='{materials}'",
                "SET_GCODE_VARIABLE MACRO=FILAMENT_MANAGER_SPOOL_STATE "
                f"VARIABLE=manual_spools VALUE='{manual_spools}'",
                "SET_GCODE_VARIABLE MACRO=FILAMENT_MANAGER_SPOOL_STATE "
                f"VARIABLE=print_temperatures VALUE='{print_temperatures}'",
                "SET_GCODE_VARIABLE MACRO=FILAMENT_MANAGER_SPOOL_STATE "
                f"VARIABLE=temperatures VALUE='{temperatures}'",
                "SET_GCODE_VARIABLE MACRO=FILAMENT_MANAGER_SPOOL_STATE "
                f"VARIABLE=catalog_revision VALUE='\"{revision}\"'",
                f"SAVE_VARIABLE VARIABLE=filament_manager_spool_catalog VALUE='{materials}'",
                f"SAVE_VARIABLE VARIABLE=filament_manager_manual_spools VALUE='{manual_spools}'",
                "SAVE_VARIABLE VARIABLE=filament_manager_spool_print_temperatures "
                f"VALUE='{print_temperatures}'",
                f"SAVE_VARIABLE VARIABLE=filament_manager_spool_temperatures VALUE='{temperatures}'",
                f"SAVE_VARIABLE VARIABLE=filament_manager_spool_catalog_revision VALUE='\"{revision}\"'",
                "SET_GCODE_VARIABLE MACRO=FILAMENT_MANAGER_SPOOL_STATE "
                f"VARIABLE=inspection_policy VALUE='\"{inspection_policy}\"'",
                "SAVE_VARIABLE VARIABLE=filament_manager_gcode_inspection_policy "
                f"VALUE='\"{inspection_policy}\"'",
            )
        )
        return await self._post("/printer/gcode/script", {"script": script})

    async def initialize_spool_preflight_state(
        self, *, spoolman_id: int | None, temperature_c: Decimal | None
    ) -> dict[str, Any]:
        """Seed persistent physical state once from the existing active Spoolman spool."""

        if spoolman_id is not None and spoolman_id <= 0:
            raise ValueError("spoolman_id must be positive")
        temperature = temperature_c or Decimal("0")
        if temperature < 0 or temperature > 500:
            raise ValueError("temperature_c is outside the supported range")
        script = (
            "FILAMENT_MANAGER_SYNC_LOADED_SPOOL "
            f"ID={spoolman_id if spoolman_id is not None else -1} "
            f"TEMP={format(temperature, 'f')} INITIALIZED=1"
        )
        return await self._post("/printer/gcode/script", {"script": script})

    async def request_spool_change(
        self, *, spoolman_id: int, temperature_c: Decimal, prompt_label: str
    ) -> dict[str, Any]:
        """Ask Klipper to perform a physical, confirmed spool change."""

        if spoolman_id <= 0:
            raise ValueError("spoolman_id must be positive")
        if temperature_c <= 0 or temperature_c > 500:
            raise ValueError("temperature_c is outside the supported range")
        if SPOOL_PROMPT_LABEL_PATTERN.fullmatch(prompt_label) is None:
            raise ValueError("prompt_label contains unsupported characters")
        script = (
            f"FILAMENT_MANAGER_CHANGE_SPOOL ID={spoolman_id} "
            f"TEMP={format(temperature_c, 'f')} LABEL={prompt_label}"
        )
        return await self._post("/printer/gcode/script", {"script": script})

    async def request_spoolman_target(
        self, *, spoolman_id: int, temperature_c: Decimal, prompt_label: str
    ) -> dict[str, Any]:
        """Turn a direct Spoolman selection into a guarded Fluidd confirmation."""

        if spoolman_id <= 0:
            raise ValueError("spoolman_id must be positive")
        if temperature_c <= 0 or temperature_c > 500:
            raise ValueError("temperature_c is outside the supported range")
        if SPOOL_PROMPT_LABEL_PATTERN.fullmatch(prompt_label) is None:
            raise ValueError("prompt_label contains unsupported characters")
        script = (
            f"FILAMENT_MANAGER_SPOOLMAN_TARGET ID={spoolman_id} "
            f"TEMP={format(temperature_c, 'f')} LABEL={prompt_label}"
        )
        return await self._post("/printer/gcode/script", {"script": script})

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
