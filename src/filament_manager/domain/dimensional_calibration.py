"""Measurement-safe dimensional calibration calculations for Cura."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class DimensionalCalibrationError(ValueError):
    """Raised when size-and-hole measurements cannot produce safe compensation."""


@dataclass(frozen=True, slots=True)
class DimensionalCalibrationResult:
    """Material compensation plus non-applying printer-geometry recommendations."""

    xy_offset: Decimal
    hole_xy_offset: Decimal
    x_horizontal_expansion: Decimal
    y_horizontal_expansion: Decimal
    axis_difference: Decimal
    axis_warning: bool
    shaft_horizontal_expansion: Decimal
    shaft_difference: Decimal
    shaft_warning: bool
    recommended_flow_percent: Decimal
    printer_x_correction_percent: Decimal
    printer_y_correction_percent: Decimal
    printer_z_correction_percent: Decimal
    material_shrinkage_x_percent: Decimal
    material_shrinkage_y_percent: Decimal
    material_shrinkage_z_percent: Decimal
    correction_classification: str


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
    design_z = _positive_decimal(inputs, "design_z_mm")
    measured_z = _positive_decimal(inputs, "measured_z_mm")
    design_hole = _positive_decimal(inputs, "design_hole_mm")
    measured_hole = _positive_decimal(inputs, "measured_hole_mm")
    design_shaft = _positive_decimal(inputs, "design_shaft_mm")
    measured_shaft = _positive_decimal(inputs, "measured_shaft_mm")
    design_wall = _positive_decimal(inputs, "design_wall_thickness_mm")
    measured_wall = _positive_decimal(inputs, "measured_wall_thickness_mm")
    baseline_flow = _positive_decimal(inputs, "baseline_flow_percent")

    x_expansion = (design_x - measured_x) / Decimal("2")
    y_expansion = (design_y - measured_y) / Decimal("2")
    shaft_expansion = (design_shaft - measured_shaft) / Decimal("2")
    axis_difference = abs(x_expansion - y_expansion)
    shaft_difference = abs(((x_expansion + y_expansion) / Decimal("2")) - shaft_expansion)
    axis_warning = axis_difference > axis_warning_threshold_mm
    shaft_warning = shaft_difference > axis_warning_threshold_mm
    return DimensionalCalibrationResult(
        xy_offset=(x_expansion + y_expansion) / Decimal("2"),
        hole_xy_offset=(design_hole - measured_hole) / Decimal("2"),
        x_horizontal_expansion=x_expansion,
        y_horizontal_expansion=y_expansion,
        axis_difference=axis_difference,
        axis_warning=axis_warning,
        shaft_horizontal_expansion=shaft_expansion,
        shaft_difference=shaft_difference,
        shaft_warning=shaft_warning,
        recommended_flow_percent=baseline_flow * design_wall / measured_wall,
        printer_x_correction_percent=design_x / measured_x * Decimal("100"),
        printer_y_correction_percent=design_y / measured_y * Decimal("100"),
        printer_z_correction_percent=design_z / measured_z * Decimal("100"),
        material_shrinkage_x_percent=(design_x - measured_x) / design_x * Decimal("100"),
        material_shrinkage_y_percent=(design_y - measured_y) / design_y * Decimal("100"),
        material_shrinkage_z_percent=(design_z - measured_z) / design_z * Decimal("100"),
        correction_classification=(
            "printer_geometry_review" if axis_warning or shaft_warning else "material_compensation"
        ),
    )
