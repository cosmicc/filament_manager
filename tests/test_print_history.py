"""Exact print-state calculation and Moonraker status tests."""

from decimal import Decimal

from filament_manager.models.enums import PrintJobStatus
from filament_manager.services.print_history import _actual_weight_g, _history_status


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
