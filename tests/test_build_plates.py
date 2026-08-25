"""Build-plate identifier and Moonraker bed-mesh contract tests."""

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from io import BytesIO
from typing import Any

import httpx
import pytest
import respx
from PIL import Image

from filament_manager.api import dependencies
from filament_manager.api.routes import operations
from filament_manager.api.routes.plates import _sanitize_plate_image
from filament_manager.clients.moonraker import (
    MoonrakerClient,
    MoonrakerError,
    MoonrakerOperationalState,
)
from filament_manager.config import PrinterConfig, Settings
from filament_manager.domain.build_plates import (
    MAX_DISCOVERED_PLATE_SURFACES,
    BuildPlateDiscoveryError,
    discover_build_plate_surface_codes,
    is_build_plate_code,
    is_build_plate_surface_code,
    split_build_plate_surface_code,
)
from filament_manager.domain.spool_preflight import SpoolPreflightCatalog
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


def dashboard_test_settings() -> Settings:
    """Return application settings for isolated dashboard-state tests."""

    return Settings.model_validate(
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


def test_uploaded_plate_images_are_sanitized_and_bounded() -> None:
    """Plate pictures are decoded and re-encoded instead of storing uploads verbatim."""

    source = BytesIO()
    Image.new("RGB", (1800, 900), "#2F80A5").save(source, format="PNG")

    sanitized = _sanitize_plate_image(source.getvalue())

    assert sanitized[:4] == b"RIFF"
    with Image.open(BytesIO(sanitized)) as image:
        assert image.format == "WEBP"
        assert image.size == (1024, 512)
    with pytest.raises(ValueError, match="valid PNG, JPEG, or WebP"):
        _sanitize_plate_image(b"not an image")


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
async def test_moonraker_active_spool_reads_supported_endpoint() -> None:
    """The active-spool reader accepts a tracked ID and an explicit clear."""

    route = respx.get("http://moonraker.test:7125/server/spoolman/spool_id").mock(
        side_effect=[
            httpx.Response(200, json={"result": {"spool_id": 17}}),
            httpx.Response(200, json={"result": {"spool_id": None}}),
        ]
    )
    client = MoonrakerClient(printer_config())

    assert await client.active_spool_id() == 17
    assert await client.active_spool_id() is None
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_moonraker_active_spool_rejects_malformed_id() -> None:
    """Malformed integration state cannot select an arbitrary canonical spool."""

    respx.get("http://moonraker.test:7125/server/spoolman/spool_id").mock(
        return_value=httpx.Response(200, json={"result": {"spool_id": "17"}})
    )

    with pytest.raises(MoonrakerError, match="invalid active spool ID"):
        await MoonrakerClient(printer_config()).active_spool_id()


@respx.mock
@pytest.mark.asyncio
async def test_moonraker_reads_persistent_physical_spool_state() -> None:
    """Only the bounded app macro fields become authoritative physical state."""

    route = respx.post("http://moonraker.test:7125/printer/objects/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "status": {
                        "gcode_macro FILAMENT_MANAGER_SPOOL_STATE": {
                            "restored": 1,
                            "initialized": 1,
                            "phase": "idle",
                            "loaded_spool_id": 17,
                            "catalog_revision": "a" * 64,
                        }
                    }
                }
            },
        )
    )

    state = await MoonrakerClient(printer_config()).spool_preflight_state()

    assert state is not None
    assert state.restored is True
    assert state.initialized is True
    assert state.loaded_spool_id == 17
    assert state.catalog_revision == "a" * 64
    assert route.calls.last.request.read() == (
        b'{"objects":{"gcode_macro FILAMENT_MANAGER_SPOOL_STATE":'
        b'["restored","initialized","phase","loaded_spool_id","catalog_revision",'
        b'"material_guid","start_bed_temp","start_extruder_temp","start_chamber_temp",'
        b'"inspection_policy","start_pending"]}}'
    )


@respx.mock
@pytest.mark.asyncio
async def test_moonraker_sends_bounded_catalog_and_physical_change_macro() -> None:
    """Catalog and change requests use one supported G-code script endpoint."""

    route = respx.post("http://moonraker.test:7125/printer/gcode/script").mock(
        return_value=httpx.Response(200, json={"result": "ok"})
    )
    materials = {"11111111-2222-3333-4444-555555555555": [[17, "FM-001-PLA-Blue"]]}
    temperatures = {"17": "215.0"}
    catalog = SpoolPreflightCatalog(
        materials=materials,
        manual_spools=[[17, "FM-001-PLA-Blue"]],
        print_temperatures={"17": "215.0"},
        temperatures=temperatures,
        revision="a" * 64,
    )
    client = MoonrakerClient(printer_config())

    await client.synchronize_spool_preflight_catalog(catalog)
    catalog_script = json.loads(route.calls.last.request.content)["script"]
    assert 'VARIABLE=catalog VALUE=\'{"11111111-2222-3333-4444-555555555555"' in catalog_script
    assert "filament_manager_manual_spools" in catalog_script
    assert "filament_manager_spool_print_temperatures" in catalog_script
    assert "filament_manager_spool_temperatures" in catalog_script
    await client.request_spool_change(
        spoolman_id=17,
        temperature_c=Decimal("215"),
        prompt_label="FM-001-PLA-Blue",
    )
    assert json.loads(route.calls.last.request.content) == {
        "script": "FILAMENT_MANAGER_CHANGE_SPOOL ID=17 TEMP=215 LABEL=FM-001-PLA-Blue"
    }
    await client.request_spoolman_target(
        spoolman_id=17,
        temperature_c=Decimal("215"),
        prompt_label="FM-001-PLA-Blue",
    )
    assert json.loads(route.calls.last.request.content) == {
        "script": "FILAMENT_MANAGER_SPOOLMAN_TARGET ID=17 TEMP=215 LABEL=FM-001-PLA-Blue"
    }
    with pytest.raises(ValueError, match="unsupported"):
        await client.request_spool_change(
            spoolman_id=17,
            temperature_c=Decimal("215"),
            prompt_label="FM-001|CANCEL_PRINT",
        )


@respx.mock
@pytest.mark.asyncio
async def test_moonraker_printer_information_uses_documented_fields() -> None:
    """Printer discovery reads server, printer, configfile, and toolhead data only."""

    respx.get("http://moonraker.test:7125/server/info").mock(
        return_value=httpx.Response(200, json={"result": {"moonraker_version": "v0.9.3"}})
    )
    respx.get("http://moonraker.test:7125/printer/info").mock(
        return_value=httpx.Response(
            200,
            json={"result": {"hostname": "flsun", "software_version": "v0.13", "state": "ready"}},
        )
    )
    route = respx.post("http://moonraker.test:7125/printer/objects/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "status": {
                        "configfile": {
                            "settings": {
                                "printer": {"kinematics": "delta"},
                                "extruder": {"nozzle_diameter": 0.4},
                            }
                        },
                        "toolhead": {
                            "axis_minimum": [-130, -130, 0],
                            "axis_maximum": [130, 130, 410],
                            "cone_start_z": 100,
                        },
                    }
                }
            },
        )
    )

    information = await MoonrakerClient(printer_config()).printer_information()

    assert information.server_info["moonraker_version"] == "v0.9.3"
    assert information.printer_info["software_version"] == "v0.13"
    assert information.object_status["configfile"]["settings"]["printer"]["kinematics"] == "delta"
    assert route.calls.last.request.read() == (
        b'{"objects":{"configfile":["settings"],"toolhead":["axis_minimum","axis_maximum","cone_start_z"]}}'
    )


@respx.mock
@pytest.mark.asyncio
async def test_moonraker_operational_state_reports_progress_and_temperatures() -> None:
    """The dashboard reader uses only advertised Klipper objects and bounded values."""

    respx.get("http://moonraker.test:7125/printer/info").mock(
        return_value=httpx.Response(200, json={"result": {"state": "ready"}})
    )
    respx.get("http://moonraker.test:7125/printer/objects/list").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "objects": [
                        "print_stats",
                        "virtual_sdcard",
                        "extruder",
                        "heater_bed",
                        "temperature_sensor chamber",
                        "temperature_sensor electronics",
                    ]
                }
            },
        )
    )
    query_route = respx.post("http://moonraker.test:7125/printer/objects/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "status": {
                        "print_stats": {"filename": "jobs/calibration_cube.gcode", "state": "printing"},
                        "virtual_sdcard": {"progress": 0.427},
                        "extruder": {"temperature": 214.6, "target": 220},
                        "heater_bed": {"temperature": 59.8, "target": 60},
                        "temperature_sensor chamber": {"temperature": 37.2},
                    }
                }
            },
        )
    )

    state = await MoonrakerClient(printer_config()).operational_state()

    assert state.klipper_state == "ready"
    assert state.print_state == "printing"
    assert state.filename == "calibration_cube.gcode"
    assert state.progress_percent == Decimal("42.700")
    assert state.nozzle_temperature_c == Decimal("214.6")
    assert state.nozzle_target_c == Decimal("220")
    assert state.bed_temperature_c == Decimal("59.8")
    assert state.chamber_temperature_c == Decimal("37.2")
    assert state.chamber_target_c is None
    assert json.loads(query_route.calls.last.request.content) == {
        "objects": {
            "print_stats": ["filename", "state"],
            "extruder": ["temperature", "target"],
            "heater_bed": ["temperature", "target"],
            "virtual_sdcard": ["progress"],
            "temperature_sensor chamber": ["temperature", "target"],
        }
    }


@respx.mock
@pytest.mark.asyncio
async def test_moonraker_operational_state_keeps_klipper_startup_visible() -> None:
    """A reachable Moonraker can report printer startup without querying unavailable objects."""

    respx.get("http://moonraker.test:7125/printer/info").mock(
        return_value=httpx.Response(200, json={"result": {"state": "startup"}})
    )

    state = await MoonrakerClient(printer_config()).operational_state()

    assert state.klipper_state == "startup"
    assert state.print_state is None
    assert state.nozzle_temperature_c is None


@pytest.mark.asyncio
async def test_dashboard_maps_live_printing_state_without_exposing_connection_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dashboard state includes useful live values and only the configured display name."""

    settings = dashboard_test_settings()

    class FakeMoonrakerClient:
        def __init__(self, _printer: PrinterConfig, timeout: float) -> None:
            assert timeout == 3

        async def operational_state(self) -> MoonrakerOperationalState:
            return MoonrakerOperationalState(
                klipper_state="ready",
                print_state="printing",
                filename="test.gcode",
                progress_percent=Decimal("64"),
                nozzle_temperature_c=Decimal("220"),
                nozzle_target_c=Decimal("220"),
                bed_temperature_c=Decimal("60"),
                bed_target_c=Decimal("60"),
                chamber_temperature_c=Decimal("38"),
                chamber_target_c=None,
            )

    monkeypatch.setattr(operations, "get_settings", lambda: settings)
    monkeypatch.setattr(operations, "MoonrakerClient", FakeMoonrakerClient)

    state = await operations._dashboard_printer_state()

    assert state.printer_name == "Test Printer"
    assert state.connection_status == "connected"
    assert state.operational_status == "printing"
    assert state.progress_percent == Decimal("64")
    assert "moonraker.test" not in state.model_dump_json()


@pytest.mark.parametrize(
    ("klipper_state", "print_state", "expected"),
    [
        ("ready", "standby", "idle"),
        ("ready", "paused", "paused"),
        ("ready", "complete", "finished"),
        ("ready", "cancelled", "cancelled"),
        ("ready", "error", "error"),
        ("startup", None, "starting"),
        ("shutdown", None, "error"),
    ],
)
@pytest.mark.asyncio
async def test_dashboard_maps_bounded_operational_states(
    monkeypatch: pytest.MonkeyPatch,
    klipper_state: str,
    print_state: str | None,
    expected: str,
) -> None:
    """Every supported Klipper/print state receives a stable dashboard label."""

    class FakeMoonrakerClient:
        def __init__(self, _printer: PrinterConfig, timeout: float) -> None:
            assert timeout == 3

        async def operational_state(self) -> MoonrakerOperationalState:
            return MoonrakerOperationalState(
                klipper_state=klipper_state,
                print_state=print_state,
                filename=None,
                progress_percent=None,
                nozzle_temperature_c=None,
                nozzle_target_c=None,
                bed_temperature_c=None,
                bed_target_c=None,
                chamber_temperature_c=None,
                chamber_target_c=None,
            )

    monkeypatch.setattr(operations, "get_settings", dashboard_test_settings)
    monkeypatch.setattr(operations, "MoonrakerClient", FakeMoonrakerClient)

    state = await operations._dashboard_printer_state()

    assert state.connection_status == "connected"
    assert state.operational_status == expected


@pytest.mark.asyncio
async def test_dashboard_degrades_only_live_telemetry_when_moonraker_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Moonraker outage produces bounded state instead of failing the dashboard route."""

    class UnavailableMoonrakerClient:
        def __init__(self, _printer: PrinterConfig, timeout: float) -> None:
            assert timeout == 3

        async def operational_state(self) -> MoonrakerOperationalState:
            raise MoonrakerError("sanitized test outage")

    monkeypatch.setattr(operations, "get_settings", dashboard_test_settings)
    monkeypatch.setattr(operations, "MoonrakerClient", UnavailableMoonrakerClient)

    state = await operations._dashboard_printer_state()

    assert state.connection_status == "unavailable"
    assert state.operational_status == "unavailable"
    assert state.klipper_state is None


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
