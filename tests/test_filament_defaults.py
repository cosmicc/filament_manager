"""Exact arithmetic and safety bounds for shared filament projection defaults."""

from decimal import Decimal

import pytest

from filament_manager.services.filament_defaults import ProductCostBasis, _spoolman_temperature


def test_scaled_product_price_does_not_round_through_a_kilogram_price() -> None:
    basis = ProductCostBasis(Decimal("1") / Decimal("3000"), "USD", 1)
    assert basis.price_for_weight(Decimal("1000")) == Decimal("0.33")
    assert basis.price_for_weight(Decimal("3000")) == Decimal("1.00")


@pytest.mark.parametrize(
    ("value", "maximum", "expected"),
    [
        ("0", 200, 0),
        ("60.4", 200, 60),
        ("215.5", 500, 216),
        ("-1", 500, None),
        ("201", 200, None),
        ("501", 500, None),
        ("NaN", 500, None),
        ("Infinity", 500, None),
    ],
)
def test_spoolman_temperature_is_bounded_and_whole_degrees(
    value: str,
    maximum: int,
    expected: int | None,
) -> None:
    assert _spoolman_temperature(Decimal(value), maximum) == expected
