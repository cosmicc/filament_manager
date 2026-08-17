"""Exact print-state calculation and Moonraker status tests."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from filament_manager.models.enums import PrintJobStatus
from filament_manager.services.print_history import _actual_weight_g, _history_status
from filament_manager.workers import dispatcher


def test_current_and_historical_completion_states_share_one_status() -> None:
    """Moonraker's current `complete` and history `completed` spellings converge."""

    assert _history_status("complete") == PrintJobStatus.COMPLETED
    assert _history_status("completed") == PrintJobStatus.COMPLETED
    assert _history_status("cancelled") == PrintJobStatus.CANCELLED
    assert _history_status("error") == PrintJobStatus.FAILED
    assert _history_status("future-value") == PrintJobStatus.LEGACY_UNKNOWN


def test_actual_weight_uses_the_captured_material_not_mutable_current_data() -> None:
    """Filament length becomes weight from density/diameter stored in the job snapshot."""

    weight = _actual_weight_g(
        Decimal("1000"),
        {"filament": {"diameter_mm": "1.75", "density_g_cm3": "1.24"}},
    )

    assert weight is not None
    assert weight.quantize(Decimal("0.001")) == Decimal("2.983")


def test_actual_weight_stays_unknown_for_legacy_unresolved_material() -> None:
    """Legacy history never invents an exact material density."""

    assert _actual_weight_g(Decimal("1000"), {"legacy_unresolved": True}) is None


@pytest.mark.asyncio
async def test_history_reconciliation_reloads_printer_after_capture_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed live capture must not reuse SQLAlchemy state expired by rollback."""

    class ExpiringPrinter:
        def __init__(self, printer_id: UUID, printer_code: str) -> None:
            self._id = printer_id
            self._printer_code = printer_code
            self.expired = False

        @property
        def id(self) -> UUID:
            if self.expired:
                raise AssertionError("expired printer id was accessed")
            return self._id

        @property
        def printer_code(self) -> str:
            if self.expired:
                raise AssertionError("expired printer code was accessed")
            return self._printer_code

    printer_id = uuid4()
    original = ExpiringPrinter(printer_id, "test-printer")
    replacement = SimpleNamespace(id=printer_id, printer_code="test-printer")

    class FakeSession:
        async def rollback(self) -> None:
            original.expired = True

        async def get(self, _model: object, object_id: UUID) -> object | None:
            assert object_id == printer_id
            return replacement

    class FakeClient:
        def __init__(self, _configured: object) -> None:
            pass

        async def print_state(self) -> object:
            return SimpleNamespace(state="standby")

        async def spool_preflight_state(self) -> None:
            return None

    async def bindings(_session: object) -> list[tuple[object, object]]:
        return [(original, SimpleNamespace(id="test-printer"))]

    async def fail_live_capture(*_args: object, **_kwargs: object) -> None:
        raise ValueError("bounded live capture failure")

    synchronized_printers: list[object] = []

    async def synchronize_history(*_args: object, **kwargs: object) -> int:
        synchronized_printers.append(kwargs["printer"])
        return 0

    monkeypatch.setattr(dispatcher, "_configured_printer_bindings", bindings)
    monkeypatch.setattr(dispatcher, "MoonrakerClient", FakeClient)
    monkeypatch.setattr(dispatcher, "synchronize_live_print", fail_live_capture)
    monkeypatch.setattr(dispatcher, "synchronize_print_history", synchronize_history)

    with pytest.raises(RuntimeError, match="ValueError"):
        await dispatcher._reconcile_moonraker_print_history(  # type: ignore[arg-type]
            FakeSession(),
            SimpleNamespace(id=uuid4()),
        )

    assert synchronized_printers == [replacement]
