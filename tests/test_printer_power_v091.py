"""Power-on requests remain exact-device, administrator-owned, and fail closed."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from filament_manager.api.routes import operations
from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError


@pytest.mark.asyncio
async def test_power_client_uses_only_configured_device(monkeypatch):
    client = object.__new__(MoonrakerClient)
    client.power_device = "printer-two"
    post = AsyncMock(return_value={"result": {"printer-two": "on"}})
    monkeypatch.setattr(client, "_post", post)
    await client.power_on()
    post.assert_awaited_once_with("/machine/device_power/device", {"device": "printer-two", "action": "on"})
    post.return_value = {"result": {"printer-one": "on"}}
    with pytest.raises(MoonrakerError):
        await client.power_on()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["off", "on", "init", "error", None])
async def test_power_route_requires_fresh_off(monkeypatch, state):
    printer_id = uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(id=printer_id, printer_code="second")),
        commit=AsyncMock(),
    )
    selected = SimpleNamespace(id="second", power_device="second-switch")
    monkeypatch.setattr(
        operations,
        "configured_printers",
        AsyncMock(
            return_value=[
                SimpleNamespace(id="first", power_device="first-switch"),
                selected,
            ]
        ),
    )
    client = SimpleNamespace(printer_power_state=AsyncMock(return_value=state), power_on=AsyncMock())
    factory = Mock(return_value=client)
    audit = Mock()
    monkeypatch.setattr(operations, "MoonrakerClient", factory)
    monkeypatch.setattr(operations, "add_audit_event", audit)
    arguments = (
        printer_id,
        SimpleNamespace(state=SimpleNamespace(correlation_id="test")),
        SimpleNamespace(id=uuid4()),
        session,
    )
    if state == "off":
        assert await operations.power_on_printer(*arguments) == {"status": "on"}
        client.power_on.assert_awaited_once()
        audit.assert_called_once()
        session.commit.assert_awaited_once()
    else:
        with pytest.raises(operations.ApiError):
            await operations.power_on_printer(*arguments)
        client.power_on.assert_not_awaited()
        audit.assert_not_called()
        session.commit.assert_not_awaited()
    factory.assert_called_once_with(selected, timeout=3)
