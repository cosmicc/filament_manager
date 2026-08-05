"""Deterministic canonical mass-policy tests."""

from decimal import Decimal

import pytest

from filament_manager.domain.mass import (
    InvalidWeightError,
    MeasurementConfirmationRequired,
    calculate_measurement,
    estimated_length_m,
)
from filament_manager.models.enums import SpoolStatus


def measurement(**overrides: object):
    values: dict[str, object] = {
        "gross_mass_g": Decimal("950"),
        "tare_mass_g": Decimal("200"),
        "nominal_mass_g": Decimal("1000"),
        "expected_remaining_g": Decimal("800"),
        "low_threshold_percent": Decimal("25"),
        "increase_tolerance_percent": Decimal("5"),
        "increase_tolerance_g": Decimal("25"),
        "confirmed": False,
    }
    values.update(overrides)
    return calculate_measurement(**values)  # type: ignore[arg-type]


def test_physical_measurement_uses_gross_minus_tare() -> None:
    result = measurement()
    assert result.net_mass_g == Decimal("750.000")
    assert result.variance_g == Decimal("-50.000")
    assert result.spool_status is SpoolStatus.IN_STOCK


def test_low_and_empty_thresholds() -> None:
    assert measurement(gross_mass_g=Decimal("400")).spool_status is SpoolStatus.LOW
    assert measurement(gross_mass_g=Decimal("200")).spool_status is SpoolStatus.EMPTY


def test_suspicious_increase_requires_explicit_confirmation() -> None:
    with pytest.raises(MeasurementConfirmationRequired):
        measurement(gross_mass_g=Decimal("1100"))
    accepted = measurement(gross_mass_g=Decimal("1100"), confirmed=True)
    assert accepted.requires_confirmation is True


def test_mass_above_nominal_requires_an_override() -> None:
    with pytest.raises(InvalidWeightError, match="nominal capacity"):
        measurement(gross_mass_g=Decimal("1250"), confirmed=True)
    result = measurement(
        gross_mass_g=Decimal("1250"),
        confirmed=True,
        allow_above_nominal=True,
    )
    assert result.net_mass_g == Decimal("1050.000")


def test_gross_mass_cannot_be_below_tare() -> None:
    with pytest.raises(InvalidWeightError, match="below tare"):
        measurement(gross_mass_g=Decimal("199"))


def test_length_estimate_is_positive_and_repeatable() -> None:
    assert estimated_length_m(Decimal("1000"), Decimal("1.24"), Decimal("1.75")) == Decimal("335.28")
