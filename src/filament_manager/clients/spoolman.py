"""Async Spoolman REST client using only the supported `/api/v1` contract."""

from typing import Any

import httpx

from filament_manager.config import SpoolmanConfig
from filament_manager.domain.spoolman import (
    decode_text_extra_field,
    encode_managed_extra_fields,
    merge_extra_fields,
)

QueryParameter = str | int | float | bool | None


class SpoolmanError(RuntimeError):
    """Sanitized Spoolman transport or API failure."""


class SpoolmanNotFoundError(SpoolmanError):
    """A previously projected Spoolman record no longer exists."""


MANAGED_EXTRA_FIELDS: dict[str, dict[str, str]] = {
    "vendor": {
        "filament_manager_vendor_uuid": "Filament Manager vendor UUID",
    },
    "filament": {
        "filament_manager_product_uuid": "Filament Manager product UUID",
        "filler": "Filler / reinforcement",
        "finish": "Finish / effect",
        "color_name": "Color name",
        "display_palette": "Filament Manager display palette",
    },
    "spool": {
        "filament_manager_spool_uuid": "Filament Manager spool UUID",
        "sheet_spool_id": "Filament Manager spool code",
    },
}


class SpoolmanClient:
    """Bounded client for health, projection, measurement, and reconciliation."""

    def __init__(self, config: SpoolmanConfig) -> None:
        self.base_url = f"{str(config.base_url).rstrip('/')}/api/v1"
        self.timeout = config.request_timeout_seconds

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, QueryParameter] | None = None,
    ) -> httpx.Response:
        """Send one bounded request and retain response headers for pagination."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json,
                    params=params,
                )
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise SpoolmanNotFoundError(f"Spoolman {method} {path} was not found") from exc
            raise SpoolmanError(
                f"Spoolman {method} {path} failed with HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SpoolmanError(f"Spoolman {method} {path} transport failed ({type(exc).__name__})") from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, QueryParameter] | None = None,
    ) -> Any:
        response = await self._send(method, path, json=json, params=params)
        try:
            return response.json()
        except ValueError as exc:
            raise SpoolmanError(f"Spoolman {method} {path} returned invalid JSON") from exc

    async def _list_paginated(
        self,
        path: str,
        *,
        params: dict[str, QueryParameter] | None = None,
        page_size: int = 200,
    ) -> list[dict[str, Any]]:
        """Read every page using Spoolman's documented total-count header."""

        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page_params = {**(params or {}), "limit": page_size, "offset": offset}
            response = await self._send("GET", path, params=page_params)
            try:
                page = response.json()
                total = int(response.headers.get("x-total-count", len(page)))
            except (TypeError, ValueError) as exc:
                raise SpoolmanError(f"Spoolman GET {path} returned invalid pagination data") from exc
            if not isinstance(page, list) or not all(isinstance(item, dict) for item in page):
                raise SpoolmanError(f"Spoolman GET {path} returned an invalid list")
            items.extend(page)
            offset += len(page)
            if not page or offset >= total:
                return items

    @staticmethod
    def _prepare_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Copy a managed payload and encode only its custom-field values."""

        prepared = dict(payload)
        extra = prepared.get("extra")
        if isinstance(extra, dict):
            prepared["extra"] = encode_managed_extra_fields(extra)
        return prepared

    async def _extra_fields(self, entity_type: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/field/{entity_type}")
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise SpoolmanError("Spoolman custom-field lookup returned an invalid payload")
        return data

    async def ensure_managed_fields(self) -> None:
        """Idempotently provision every custom field used by projections."""

        for entity_type, definitions in MANAGED_EXTRA_FIELDS.items():
            existing = {str(item.get("key")): item for item in await self._extra_fields(entity_type)}
            for key, name in definitions.items():
                current = existing.get(key)
                if current is not None:
                    if current.get("field_type") != "text":
                        raise SpoolmanError(
                            f"Spoolman managed field {entity_type}.{key} has an incompatible type"
                        )
                    continue
                await self._request(
                    "POST",
                    f"/field/{entity_type}/{key}",
                    json={"name": name, "field_type": "text", "order": 0},
                )

    async def projection_health(self) -> dict[str, Any]:
        """Verify health plus the non-mutating managed-field projection contract."""

        health = await self.health()
        for entity_type, definitions in MANAGED_EXTRA_FIELDS.items():
            existing = {str(item.get("key")): item for item in await self._extra_fields(entity_type)}
            for key in definitions:
                current = existing.get(key)
                if current is None or current.get("field_type") != "text":
                    raise SpoolmanError("Spoolman projection fields are not ready")
        return health

    async def health(self) -> dict[str, Any]:
        """Return Spoolman's documented health response."""

        data = await self._request("GET", "/health")
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman health returned an invalid payload")
        return data

    async def find_vendors(self, name: str) -> list[dict[str, Any]]:
        """Find exact/near vendor matches by documented query parameter."""

        return await self._list_paginated("/vendor", params={"name": f'"{name}"'})

    async def list_vendors(self) -> list[dict[str, Any]]:
        """Return every vendor for duplicate-safe managed UUID discovery."""

        return await self._list_paginated("/vendor")

    async def create_vendor(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/vendor", json=self._prepare_payload(payload))
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
        payload["extra"] = merge_extra_fields(
            remote.get("extra"), encode_managed_extra_fields(payload.get("extra", {}))
        )
        data = await self._request("PATCH", f"/vendor/{vendor_id}", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman vendor update returned an invalid payload")
        return data

    async def create_filament(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/filament", json=self._prepare_payload(payload))
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
        payload["extra"] = merge_extra_fields(
            remote.get("extra"), encode_managed_extra_fields(payload.get("extra", {}))
        )
        data = await self._request("PATCH", f"/filament/{filament_id}", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman filament update returned an invalid payload")
        return data

    async def delete_filament(self, filament_id: int) -> None:
        """Delete one unused managed filament through Spoolman's supported API."""

        await self._send("DELETE", f"/filament/{filament_id}")

    async def create_spool(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/spool", json=self._prepare_payload(payload))
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
        payload["extra"] = merge_extra_fields(
            remote.get("extra"), encode_managed_extra_fields(payload.get("extra", {}))
        )
        data = await self._request("PATCH", f"/spool/{spool_id}", json=payload)
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman spool update returned an invalid payload")
        return data

    async def delete_spool(self, spool_id: int) -> None:
        """Delete one unused managed spool through Spoolman's supported API."""

        await self._send("DELETE", f"/spool/{spool_id}")

    async def measure_spool(self, spool_id: int, gross_weight_g: float) -> dict[str, Any]:
        """Submit the documented current gross-weight measurement."""

        data = await self._request("PUT", f"/spool/{spool_id}/measure", json={"weight": gross_weight_g})
        if not isinstance(data, dict):
            raise SpoolmanError("Spoolman measurement returned an invalid payload")
        return data

    async def set_spool_remaining_weight(self, spool_id: int, remaining_weight_g: float) -> dict[str, Any]:
        """Set canonical net remaining weight through Spoolman's supported update API.

        The ``/measure`` endpoint models a new physical gross-scale reading and
        requires usable tare metadata. Filament Manager has already calculated
        and validated these correction jobs as net filament mass, so the
        ``remaining_weight`` update is the matching supported contract.
        """

        return await self.update_spool(spool_id, {"remaining_weight": remaining_weight_g})

    async def list_filaments(self) -> list[dict[str, Any]]:
        """Return every filament across all Spoolman result pages."""

        return await self._list_paginated("/filament")

    async def list_spools(self) -> list[dict[str, Any]]:
        """Return every spool, including archived records, across all pages."""

        return await self._list_paginated("/spool", params={"allow_archived": True})

    @staticmethod
    def _find_by_managed_uuid(
        items: list[dict[str, Any]], key: str, expected_uuid: str
    ) -> dict[str, Any] | None:
        match: dict[str, Any] | None = None
        for item in items:
            extra = item.get("extra")
            if isinstance(extra, dict) and decode_text_extra_field(extra.get(key)) == expected_uuid:
                if match is not None:
                    raise SpoolmanError(f"Spoolman contains duplicate managed values for {key}")
                match = item
        return match

    async def find_managed_vendor(self, vendor_uuid: str) -> dict[str, Any] | None:
        return self._find_by_managed_uuid(
            await self.list_vendors(), "filament_manager_vendor_uuid", vendor_uuid
        )

    async def find_managed_filament(self, product_uuid: str) -> dict[str, Any] | None:
        return self._find_by_managed_uuid(
            await self.list_filaments(), "filament_manager_product_uuid", product_uuid
        )

    async def find_managed_spool(self, spool_uuid: str) -> dict[str, Any] | None:
        return self._find_by_managed_uuid(await self.list_spools(), "filament_manager_spool_uuid", spool_uuid)
