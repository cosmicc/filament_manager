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
