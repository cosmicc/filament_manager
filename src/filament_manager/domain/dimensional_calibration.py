"""Measurement-safe dimensional calibration calculations for Cura."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class DimensionalCalibrationError(ValueError):
    """Raised when size-and-hole measurements cannot produce safe compensation."""


@dataclass(frozen=True, slots=True)
class DimensionalCalibrationResult:
    """Cura compensation values plus the independent X and Y observations."""

    xy_offset: Decimal
    hole_xy_offset: Decimal
    x_horizontal_expansion: Decimal
    y_horizontal_expansion: Decimal
    axis_difference: Decimal
    axis_warning: bool


def _positive_decimal(inputs: Mapping[str, object], key: str) -> Decimal:
    value = inputs.get(key)
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise DimensionalCalibrationError(f"{key} must be a decimal measurement") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise DimensionalCalibrationError(f"{key} must be greater than zero")
    return parsed


def calculate_dimensional_compensation(
    inputs: Mapping[str, object],
    *,
    axis_warning_threshold_mm: Decimal = Decimal("0.05"),
) -> DimensionalCalibrationResult:
    """Calculate Cura horizontal expansion from design and measured dimensions.

    Cura applies horizontal expansion at both sides of an outside dimension, so
    each axis correction is half of its design-minus-measured difference. The
    single Cura Horizontal Expansion value is the mean of the X and Y corrections.
    Hole Horizontal Expansion uses the same two-sided correction for the hole.
    """

    design_x = _positive_decimal(inputs, "design_x_mm")
    measured_x = _positive_decimal(inputs, "measured_x_mm")
    design_y = _positive_decimal(inputs, "design_y_mm")
    measured_y = _positive_decimal(inputs, "measured_y_mm")
    design_hole = _positive_decimal(inputs, "design_hole_mm")
    measured_hole = _positive_decimal(inputs, "measured_hole_mm")

    x_expansion = (design_x - measured_x) / Decimal("2")
    y_expansion = (design_y - measured_y) / Decimal("2")
    axis_difference = abs(x_expansion - y_expansion)
    return DimensionalCalibrationResult(
        xy_offset=(x_expansion + y_expansion) / Decimal("2"),
        hole_xy_offset=(design_hole - measured_hole) / Decimal("2"),
        x_horizontal_expansion=x_expansion,
        y_horizontal_expansion=y_expansion,
        axis_difference=axis_difference,
        axis_warning=axis_difference > axis_warning_threshold_mm,
    )
