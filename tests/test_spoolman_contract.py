"""Supported Spoolman projection contract tests."""

import httpx
import pytest
import respx

from filament_manager.clients.spoolman import SpoolmanClient
from filament_manager.config import SpoolmanConfig
from filament_manager.domain.spoolman import merge_extra_fields


def client() -> SpoolmanClient:
    return SpoolmanClient(SpoolmanConfig(base_url="http://spoolman.test:8000"))


def test_extra_merge_preserves_remote_owned_keys() -> None:
    assert merge_extra_fields(
        {"unknown_plugin_key": "keep", "filament_manager_spool_uuid": "old"},
        {"filament_manager_spool_uuid": "new"},
    ) == {"unknown_plugin_key": "keep", "filament_manager_spool_uuid": "new"}


@pytest.mark.asyncio
@respx.mock
async def test_spool_update_reads_then_preserves_extra_fields() -> None:
    get_route = respx.get("http://spoolman.test:8000/api/v1/spool/7").mock(
        return_value=httpx.Response(200, json={"id": 7, "extra": {"remote_key": "keep"}})
    )
    patch_route = respx.patch("http://spoolman.test:8000/api/v1/spool/7").mock(
        return_value=httpx.Response(200, json={"id": 7})
    )
    await client().update_spool(7, {"location": "Rack A", "extra": {"sheet_spool_id": "G6"}})
    assert get_route.called
    assert patch_route.calls.last.request.content
    assert patch_route.calls.last.request.read().decode() == (
        '{"location":"Rack A","extra":{"remote_key":"keep","sheet_spool_id":"G6"}}'
    )


@pytest.mark.asyncio
@respx.mock
async def test_measurement_uses_documented_measure_endpoint() -> None:
    route = respx.put("http://spoolman.test:8000/api/v1/spool/7/measure").mock(
        return_value=httpx.Response(200, json={"id": 7, "remaining_weight": 750})
    )
    await client().measure_spool(7, 950)
    assert route.calls.last.request.read().decode() == '{"weight":950}'
