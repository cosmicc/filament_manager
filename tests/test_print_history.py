"""Exact print-state calculation and Moonraker status tests."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from filament_manager.models.enums import GcodeInspectionStatus, PrintJobStatus
from filament_manager.models.printing import PrintJob
from filament_manager.services import print_history
from filament_manager.services.print_costs import print_cost_summary, segment_cost
from filament_manager.services.print_history import (
    _actual_weight_g,
    _blocking_gate_passed,
    _history_status,
    _terminal_usage_targets,
)
from filament_manager.workers import dispatcher


def test_current_and_historical_completion_states_share_one_status() -> None:
    """Moonraker's current `complete` and history `completed` spellings converge."""

    assert _history_status("complete") == PrintJobStatus.COMPLETED
    assert _history_status("completed") == PrintJobStatus.COMPLETED
    assert _history_status("cancelled") == PrintJobStatus.CANCELLED
    assert _history_status("error") == PrintJobStatus.FAILED
    assert _history_status("klippy_shutdown") == PrintJobStatus.FAILED
    assert _history_status("klippy_disconnect") == PrintJobStatus.FAILED
    assert _history_status("interrupted") == PrintJobStatus.FAILED
    assert _history_status("future-value") == PrintJobStatus.LEGACY_UNKNOWN


@pytest.mark.parametrize(
    ("status", "profile_resolved", "inspection", "expected"),
    (
        (GcodeInspectionStatus.PASSED, True, {"mismatches": []}, True),
        (GcodeInspectionStatus.WARNING, True, {"mismatches": []}, True),
        (GcodeInspectionStatus.WARNING, True, {"mismatches": ["temperature"]}, False),
        (GcodeInspectionStatus.UNAVAILABLE, True, {"mismatches": []}, False),
        (GcodeInspectionStatus.BLOCKED, True, {"mismatches": []}, False),
        (GcodeInspectionStatus.PENDING, True, {"mismatches": []}, False),
        (GcodeInspectionStatus.PASSED, False, {"mismatches": []}, False),
        (GcodeInspectionStatus.PASSED, True, {}, False),
    ),
)
def test_blocking_gate_decision_is_derived_fail_closed_from_persisted_evidence(
    status: GcodeInspectionStatus,
    profile_resolved: bool,
    inspection: dict[str, object],
    expected: bool,
) -> None:
    """Only complete, exact-profile evidence without mismatches may release the gate."""

    job = PrintJob(
        inspection_status=status,
        inspected_at=datetime.now(UTC),
        material_profile_id=uuid4() if profile_resolved else None,
        inspection=inspection,
    )

    assert _blocking_gate_passed(job) is expected


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


def test_terminal_usage_aggregates_reused_spools_from_immutable_segments() -> None:
    """M600 segments that return to one spool subtract that spool's total exactly once."""

    first_spool = uuid4()
    second_spool = uuid4()
    captured_at = datetime.now(UTC)
    job = SimpleNamespace(
        segments=[
            SimpleNamespace(
                segment_number=1,
                created_at=captured_at,
                spool_id=first_spool,
                actual_filament_weight_g=Decimal("4.25"),
                state_snapshot={"spool": {"remaining_mass_g": "900"}},
            ),
            SimpleNamespace(
                segment_number=2,
                created_at=captured_at,
                spool_id=second_spool,
                actual_filament_weight_g=Decimal("3.5"),
                state_snapshot={"spool": {"remaining_mass_g": "700"}},
            ),
            SimpleNamespace(
                segment_number=3,
                created_at=captured_at,
                spool_id=first_spool,
                actual_filament_weight_g=Decimal("2.75"),
                state_snapshot={"spool": {"remaining_mass_g": "900"}},
            ),
        ]
    )

    assert _terminal_usage_targets(job) == {
        first_spool: (Decimal("900"), Decimal("7.000"), captured_at),
        second_spool: (Decimal("700"), Decimal("3.500"), captured_at),
    }


def test_print_cost_uses_each_segment_immutable_purchase_basis() -> None:
    """A material change totals compatible captured rates without current inventory reads."""

    segments = [
        SimpleNamespace(
            actual_filament_weight_g=Decimal("12.5"),
            state_snapshot={"spool": {"cost_per_gram": "0.025", "currency": "usd"}},
        ),
        SimpleNamespace(
            actual_filament_weight_g=Decimal("7.5"),
            state_snapshot={"spool": {"cost_per_gram": "0.04", "currency": "USD"}},
        ),
    ]
    job = SimpleNamespace(
        segments=segments,
        actual_filament_weight_g=Decimal("20"),
        predicted_filament_weight_g=Decimal("25"),
        state_snapshot={"spool": {"cost_per_gram": "0.025", "currency": "USD"}},
    )

    assert segment_cost(segments[0]) == (Decimal("0.025"), Decimal("0.31"), "USD")
    assert print_cost_summary(job) == {
        "actual_filament_cost": Decimal("0.61"),
        "predicted_filament_cost": Decimal("0.63"),
        "cost_currency": "USD",
        "cost_currency_conflict": False,
        "cost_complete": True,
        "priced_filament_weight_g": Decimal("20.0"),
        "unpriced_filament_weight_g": Decimal("0"),
    }


def test_print_cost_reports_unpriced_or_mixed_currency_weight_without_inventing_a_total() -> None:
    """Partial and mixed-currency jobs remain explicit instead of returning a misleading cost."""

    job = SimpleNamespace(
        segments=[
            SimpleNamespace(
                actual_filament_weight_g=Decimal("10"),
                state_snapshot={"spool": {"cost_per_gram": "0.02", "currency": "USD"}},
            ),
            SimpleNamespace(
                actual_filament_weight_g=Decimal("5"),
                state_snapshot={"spool": {"cost_per_gram": "0.03", "currency": "CAD"}},
            ),
            SimpleNamespace(actual_filament_weight_g=Decimal("2"), state_snapshot={"spool": {}}),
        ],
        actual_filament_weight_g=Decimal("17"),
        predicted_filament_weight_g=None,
        state_snapshot={},
    )

    summary = print_cost_summary(job)

    assert summary["actual_filament_cost"] is None
    assert summary["cost_currency"] is None
    assert summary["cost_currency_conflict"] is True
    assert summary["cost_complete"] is False
    assert summary["priced_filament_weight_g"] == Decimal("15")
    assert summary["unpriced_filament_weight_g"] == Decimal("2")


@pytest.mark.asyncio
async def test_malformed_history_record_does_not_block_success_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One malformed legacy row must not poison every later history pass."""

    class NestedTransaction:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> bool:
            return False

    class FakeSession:
        committed = False

        def begin_nested(self) -> NestedTransaction:
            return NestedTransaction()

        async def commit(self) -> None:
            self.committed = True

    class FakeClient:
        async def history_jobs(
            self, *, start: int, limit: int, since: float | None
        ) -> tuple[dict[str, object], ...]:
            del start, limit, since
            return (
                {"job_id": "bad", "filename": "bad.gcode", "end_time": 1_777_000_000},
                {"job_id": "good", "filename": "good.gcode", "end_time": 1_777_000_001},
            )

    calls = 0

    async def upsert(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TypeError("malformed historical segment")
        return SimpleNamespace(
            filename="good.gcode",
            thumbnail_checked_at=datetime.now(UTC),
        )

    monkeypatch.setattr(print_history, "_upsert_history_job", upsert)
    printer = SimpleNamespace(
        printer_code="test-printer",
        print_history_initialized_at=None,
        last_print_history_sync_at=None,
        last_print_history_end_at=None,
    )
    session = FakeSession()

    imported = await print_history.synchronize_print_history(  # type: ignore[arg-type]
        session,
        printer=printer,
        client=FakeClient(),  # type: ignore[arg-type]
        correlation_id="test-history",
    )

    assert imported == 1
    assert printer.last_print_history_sync_at is not None
    assert session.committed is True


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

        async def live_print_context(self) -> tuple[object, None]:
            return SimpleNamespace(state="standby"), None

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


@pytest.mark.asyncio
async def test_active_print_capture_defers_full_history_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ten-second live pass must not fetch all history during printer motion."""

    printer = SimpleNamespace(id=uuid4(), printer_code="test-printer")

    class FakeClient:
        def __init__(self, _configured: object) -> None:
            pass

        async def live_print_context(self) -> tuple[object, None]:
            return SimpleNamespace(state="printing"), None

    async def bindings(_session: object) -> list[tuple[object, object]]:
        return [(printer, SimpleNamespace(id="test-printer"))]

    live_captures = 0
    history_imports = 0

    async def synchronize_live(*_args: object, **_kwargs: object) -> None:
        nonlocal live_captures
        live_captures += 1

    async def synchronize_history(*_args: object, **_kwargs: object) -> int:
        nonlocal history_imports
        history_imports += 1
        return 0

    monkeypatch.setattr(dispatcher, "_configured_printer_bindings", bindings)
    monkeypatch.setattr(dispatcher, "MoonrakerClient", FakeClient)
    monkeypatch.setattr(dispatcher, "synchronize_live_print", synchronize_live)
    monkeypatch.setattr(dispatcher, "synchronize_print_history", synchronize_history)

    await dispatcher._reconcile_moonraker_print_history(  # type: ignore[arg-type]
        SimpleNamespace(),
        SimpleNamespace(id=uuid4()),
    )

    assert live_captures == 1
    assert history_imports == 0


@pytest.mark.asyncio
async def test_nonessential_moonraker_passes_are_deferred_during_active_print(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """State, plate, catalog, and printer-information reads pause during motion."""

    printer = SimpleNamespace(id=uuid4(), printer_code="test-printer")

    async def bindings(_session: object) -> list[tuple[object, object]]:
        return [(printer, SimpleNamespace(id="test-printer"))]

    async def active(_session: object, _printer_id: object) -> bool:
        return True

    class UnexpectedClient:
        def __init__(self, _configured: object) -> None:
            raise AssertionError("Moonraker must not be contacted by a nonessential pass")

    monkeypatch.setattr(dispatcher, "_configured_printer_bindings", bindings)
    monkeypatch.setattr(dispatcher, "_canonical_print_is_active", active)
    monkeypatch.setattr(dispatcher, "MoonrakerClient", UnexpectedClient)

    await dispatcher._reconcile_moonraker_state(  # type: ignore[arg-type]
        SimpleNamespace(), SimpleNamespace(id=uuid4())
    )
    await dispatcher._reconcile_moonraker_printer_information(  # type: ignore[arg-type]
        SimpleNamespace(), SimpleNamespace(id=uuid4())
    )
