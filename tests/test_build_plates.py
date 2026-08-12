"""Build-plate identifier and Moonraker bed-mesh contract tests."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx

from filament_manager.api import dependencies
from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.config import PrinterConfig, Settings
from filament_manager.domain.build_plates import (
    MAX_DISCOVERED_PLATE_SURFACES,
    BuildPlateDiscoveryError,
    discover_build_plate_surface_codes,
    is_build_plate_code,
    is_build_plate_surface_code,
    split_build_plate_surface_code,
)
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole


def printer_config() -> PrinterConfig:
    """Return a bounded test-only Moonraker configuration."""

    return PrinterConfig.model_validate(
        {
            "id": "test-printer",
            "name": "Test Printer",
            "base_url": "http://moonraker.test:7125",
            "websocket_url": "ws://moonraker.test:7125/websocket",
            "api_key": "test-api-key",
            "nozzle_diameter_mm": 0.4,
        }
    )


def test_discovery_accepts_exact_plate_side_codes_in_natural_order() -> None:
    """Discovery groups suffixed Side B meshes and sorts each side naturally."""

    codes, ignored = discover_build_plate_surface_codes(["P10b", "default", "P2b", "P01", "P1", "P2", "P10"])

    assert codes == ("P1", "P2", "P2b", "P10", "P10b")
    assert ignored == 2
    assert is_build_plate_code("P999")
    assert not is_build_plate_code("P999b")
    assert is_build_plate_surface_code("P999b")
    assert split_build_plate_surface_code("P4") == ("P4", "a")
    assert split_build_plate_surface_code("P4b") == ("P4", "b")
    assert not is_build_plate_code("P0")
    assert not is_build_plate_code("p1")
    assert not is_build_plate_code("P1 BED_MESH_CLEAR")


def test_discovery_rejects_an_excessive_number_of_plate_meshes() -> None:
    """A compromised integration cannot create an unbounded canonical catalog."""

    with pytest.raises(BuildPlateDiscoveryError, match="more than"):
        discover_build_plate_surface_codes(
            f"P{number}" for number in range(1, MAX_DISCOVERED_PLATE_SURFACES + 2)
        )


@respx.mock
@pytest.mark.asyncio
async def test_moonraker_bed_mesh_state_uses_supported_object_query() -> None:
    """The client extracts saved and active profiles without exposing connection details."""

    route = respx.post("http://moonraker.test:7125/printer/objects/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "eventtime": 123.4,
                    "status": {
                        "bed_mesh": {
                            "profile_name": "P10",
                            "profiles": {"default": {}, "P1": {}, "P10": {}},
                        }
                    },
                }
            },
        )
    )

    state = await MoonrakerClient(printer_config()).bed_mesh_state()

    assert state.profile_names == ("default", "P1", "P10")
    assert state.active_profile == "P10"
    request = route.calls.last.request
    assert request.headers["X-Api-Key"] == "test-api-key"
    assert request.read() == b'{"objects":{"bed_mesh":["profile_name","profiles"]}}'


@respx.mock
@pytest.mark.asyncio
async def test_moonraker_bed_mesh_state_rejects_missing_object() -> None:
    """Missing bed_mesh data fails closed with a sanitized connector error."""

    respx.post("http://moonraker.test:7125/printer/objects/query").mock(
        return_value=httpx.Response(200, json={"result": {"status": {}}})
    )

    with pytest.raises(MoonrakerError, match="did not return"):
        await MoonrakerClient(printer_config()).bed_mesh_state()


@respx.mock
@pytest.mark.asyncio
async def test_dynamic_plate_selection_allows_p10_and_rejects_gcode_input() -> None:
    """Only exact P-number values reach the command endpoint."""

    route = respx.post("http://moonraker.test:7125/printer/gcode/script").mock(
        return_value=httpx.Response(200, json={"result": "ok"})
    )
    client = MoonrakerClient(printer_config())

    await client.select_build_plate("P10b")
    with pytest.raises(ValueError, match="exact P<number>"):
        await client.select_build_plate("P10\nBED_MESH_CLEAR")

    assert route.call_count == 1
    assert route.calls.last.request.read() == b'{"script":"SELECT_BUILD_PLATE PLATE=P10b"}'


@pytest.mark.asyncio
async def test_operator_cannot_synchronize_canonical_plates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The synchronization mutation remains restricted to Administrators."""

    settings = Settings.model_validate(
        {
            "app": {
                "base_url": "http://testserver",
                "allowed_hosts": ["testserver"],
                "secure_cookies": False,
            },
            "database": {"url": "postgresql+psycopg://user:password@database.test/app"},
            "spoolman": {"base_url": "http://spoolman.test:8000"},
            "moonraker": {"printers": [printer_config().model_dump()]},
            "google": {"enabled": False},
            "sync": {},
            "plates": {"allowed_codes": ["P1", "P2", "P3", "P4", "P5"]},
            "devices": {},
            "security": {},
        }
    )
    operator = User(
        username="operator",
        normalized_username="operator",
        display_name="Operator",
        password_hash="not-used-by-this-test",
        role=UserRole.OPERATOR,
    )

    async def user_override() -> User:
        return operator

    async def session_override() -> AsyncIterator[Any]:
        yield None

    from filament_manager import main

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    app.dependency_overrides[dependencies.current_user] = user_override
    app.dependency_overrides[dependencies.session_dependency] = session_override
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/build-plates/synchronize",
            json={"printer_id": "00000000-0000-0000-0000-000000000001"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
