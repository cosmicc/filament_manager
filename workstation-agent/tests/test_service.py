"""Workstation polling isolation tests."""

import httpx
import pytest

from filament_manager_agent import service


def test_rejected_recovery_upload_does_not_block_deployment_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An independent backup failure must not stop material synchronization."""

    calls = {"deployment_claims": 0}

    class FakeClient:
        def __init__(self, _config: object) -> None:
            pass

        def heartbeat(self, _payload: object) -> None:
            return None

        def upload_recovery_snapshot(self, _payload: object) -> None:
            request = httpx.Request("POST", "https://filament-manager.invalid/snapshot")
            response = httpx.Response(422, request=request)
            raise httpx.HTTPStatusError("rejected", request=request, response=response)

        def claim_recovery_restore(self) -> None:
            return None

        def claim(self) -> None:
            calls["deployment_claims"] += 1
            return None

    monkeypatch.setattr(service, "load_config", lambda: object())
    monkeypatch.setattr(service, "AgentClient", FakeClient)
    monkeypatch.setattr(service, "discover_installations", lambda: [object()])
    monkeypatch.setattr(service, "cura_is_running", lambda: False)
    monkeypatch.setattr(service, "capture_recovery_snapshot", lambda _item: {"snapshot": True})
    monkeypatch.setattr(service, "heartbeat_payload", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "managed_material_edit_receipts", lambda _items: {})
    monkeypatch.setattr(service, "acknowledge_managed_material_edits", lambda _items: None)

    assert service.run_once() is False
    assert calls["deployment_claims"] == 1


def test_recovery_capture_failure_does_not_mark_the_whole_agent_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a safe recovery warning without using the agent-wide error field."""

    heartbeats: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, _config: object) -> None:
            pass

        def heartbeat(self, payload: dict[str, object]) -> None:
            heartbeats.append(payload)

        def claim_recovery_restore(self) -> None:
            return None

        def claim(self) -> None:
            return None

    monkeypatch.setattr(service, "load_config", lambda: object())
    monkeypatch.setattr(service, "AgentClient", FakeClient)
    monkeypatch.setattr(service, "discover_installations", lambda: [object()])
    monkeypatch.setattr(service, "cura_is_running", lambda: False)
    monkeypatch.setattr(
        service,
        "capture_recovery_snapshot",
        lambda _item: (_ for _ in ()).throw(RuntimeError("A supported Cura configuration file is invalid.")),
    )
    monkeypatch.setattr(service, "managed_material_edit_receipts", lambda _items: {})
    monkeypatch.setattr(service, "acknowledge_managed_material_edits", lambda _items: None)
    monkeypatch.setattr(service, "discover_materials", lambda _items: [])
    monkeypatch.setattr(service, "discover_print_profiles", lambda _items: [])
    monkeypatch.setattr(service, "discover_managed_materials", lambda _items: [])
    monkeypatch.setattr(service, "unmanaged_material_count", lambda _items: 0)
    monkeypatch.setattr(service, "managed_library_checksum", lambda _path: None)
    monkeypatch.setattr(service, "material_settings_sync_status", lambda _path: {})
    monkeypatch.setattr(service, "material_settings_plugin_inventory", lambda _item: [])

    installation = type(
        "Installation",
        (),
        {
            "installation_id": "cura-test",
            "data_path": object(),
            "report": lambda self: {},
        },
    )()
    monkeypatch.setattr(service, "discover_installations", lambda: [installation])

    assert service.run_once() is False
    assert len(heartbeats) == 1
    assert heartbeats[0]["last_error"] is None
    capabilities = heartbeats[0]["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["cura_recovery_capture_state"] == "error"
    assert capabilities["cura_recovery_capture_message"] == (
        "A supported Cura settings file contains invalid syntax."
    )
