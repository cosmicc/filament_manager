"""Supported Spoolman projection contract tests."""

from uuid import uuid4

import httpx
import pytest
import respx

from filament_manager.clients.spoolman import MANAGED_EXTRA_FIELDS, SpoolmanClient, SpoolmanError
from filament_manager.config import SpoolmanConfig
from filament_manager.domain.spoolman import (
    decode_text_extra_field,
    encode_managed_extra_fields,
    merge_extra_fields,
)


def client() -> SpoolmanClient:
    return SpoolmanClient(SpoolmanConfig(base_url="http://spoolman.test:8000"))


def test_extra_merge_preserves_remote_owned_keys() -> None:
    assert merge_extra_fields(
        {"unknown_plugin_key": "keep", "filament_manager_spool_uuid": "old"},
        {"filament_manager_spool_uuid": "new"},
    ) == {"unknown_plugin_key": "keep", "filament_manager_spool_uuid": "new"}


def test_managed_extra_values_are_json_encoded_and_safely_decoded() -> None:
    assert encode_managed_extra_fields(
        {"filament_manager_spool_uuid": "00000000-0000-0000-0000-000000000007"}
    ) == {"filament_manager_spool_uuid": '"00000000-0000-0000-0000-000000000007"'}
    assert decode_text_extra_field('"Bucket 17"') == "Bucket 17"
    assert decode_text_extra_field("not-json") is None
    assert decode_text_extra_field("17") is None


def test_structured_metadata_is_nested_inside_a_spoolman_text_field() -> None:
    """Managed text fields must decode to strings even when they carry compact JSON."""

    encoded = encode_managed_extra_fields(
        {"display_palette": {"mode": "multicolor", "colors": ["112233", "AABBCC"]}}
    )

    assert encoded == {
        "display_palette": '"{\\"mode\\":\\"multicolor\\",\\"colors\\":[\\"112233\\",\\"AABBCC\\"]}"'
    }
    assert decode_text_extra_field(encoded["display_palette"]) == (
        '{"mode":"multicolor","colors":["112233","AABBCC"]}'
    )


def test_duplicate_managed_uuid_is_rejected() -> None:
    managed_uuid = str(uuid4())
    items = [
        {"id": 1, "extra": {"filament_manager_spool_uuid": f'"{managed_uuid}"'}},
        {"id": 2, "extra": {"filament_manager_spool_uuid": f'"{managed_uuid}"'}},
    ]

    with pytest.raises(RuntimeError, match="duplicate managed values"):
        SpoolmanClient._find_by_managed_uuid(
            items,
            "filament_manager_spool_uuid",
            managed_uuid,
        )


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
        '{"location":"Rack A","extra":{"remote_key":"keep","sheet_spool_id":"\\"G6\\""}}'
    )


@pytest.mark.asyncio
@respx.mock
async def test_managed_fields_are_provisioned_idempotently() -> None:
    for entity_type, definitions in MANAGED_EXTRA_FIELDS.items():
        respx.get(f"http://spoolman.test:8000/api/v1/field/{entity_type}").mock(
            return_value=httpx.Response(200, json=[])
        )
        for key in definitions:
            route = respx.post(f"http://spoolman.test:8000/api/v1/field/{entity_type}/{key}").mock(
                return_value=httpx.Response(200, json=[])
            )

    await client().ensure_managed_fields()

    assert route.called
    assert route.calls.last.request.read().decode().endswith('"field_type":"text","order":0}')


@pytest.mark.asyncio
@respx.mock
async def test_spool_list_reads_every_page_and_includes_archived() -> None:
    route = respx.get("http://spoolman.test:8000/api/v1/spool").mock(
        side_effect=[
            httpx.Response(200, json=[{"id": 1}, {"id": 2}], headers={"x-total-count": "3"}),
            httpx.Response(200, json=[{"id": 3}], headers={"x-total-count": "3"}),
        ]
    )

    assert [item["id"] for item in await client().list_spools()] == [1, 2, 3]
    assert route.calls[0].request.url.params["offset"] == "0"
    assert route.calls[1].request.url.params["offset"] == "2"
    assert route.calls[0].request.url.params["allow_archived"] == "true"


@pytest.mark.asyncio
@respx.mock
async def test_measurement_uses_documented_measure_endpoint() -> None:
    route = respx.put("http://spoolman.test:8000/api/v1/spool/7/measure").mock(
        return_value=httpx.Response(200, json={"id": 7, "remaining_weight": 750})
    )
    await client().measure_spool(7, 950)
    assert route.calls.last.request.read().decode() == '{"weight":950}'


@pytest.mark.asyncio
@respx.mock
async def test_remaining_weight_correction_uses_supported_spool_update() -> None:
    """Canonical net corrections must not use the gross-scale measurement route."""

    respx.get("http://spoolman.test:8000/api/v1/spool/7").mock(
        return_value=httpx.Response(200, json={"id": 7, "extra": {}})
    )
    route = respx.patch("http://spoolman.test:8000/api/v1/spool/7").mock(
        return_value=httpx.Response(200, json={"id": 7, "remaining_weight": 750})
    )

    await client().set_spool_remaining_weight(7, 750)

    assert route.calls.last.request.read().decode() == '{"remaining_weight":750,"extra":{}}'


@pytest.mark.asyncio
@respx.mock
async def test_spoolman_http_failure_retains_status_without_response_body() -> None:
    """Diagnostics need a safe status code but must never include an upstream body."""

    respx.get("http://spoolman.test:8000/api/v1/spool/7").mock(
        return_value=httpx.Response(400, json={"message": "private upstream detail"})
    )

    with pytest.raises(SpoolmanError, match=r"GET /spool/7 failed with HTTP 400") as raised:
        await client().get_spool(7)

    assert "private upstream detail" not in str(raised.value)
