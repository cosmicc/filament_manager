"""Ordered seven-step calibration policy and dimensional-math tests."""

from decimal import Decimal

from filament_manager.domain.calibration import CALIBRATION_STEPS, invalidated_statuses, ready_to_publish
from filament_manager.domain.dimensional_calibration import calculate_dimensional_compensation
from filament_manager.models.enums import CalibrationStepStatus


def test_workflow_preserves_exact_seven_steps() -> None:
    assert [(step.order, step.key, step.required) for step in CALIBRATION_STEPS] == [
        (1, "temperature", True),
        (2, "flow", True),
        (3, "pressure_advance", True),
        (4, "retraction", True),
        (5, "dimensional", True),
        (6, "overhang", True),
        (7, "ironing", False),
    ]


def test_optional_ironing_does_not_block_publication() -> None:
    statuses = {
        step.key: (CalibrationStepStatus.COMPLETED if step.required else CalibrationStepStatus.NOT_STARTED)
        for step in CALIBRATION_STEPS
    }
    assert ready_to_publish(statuses) is True


def test_incomplete_required_step_blocks_publication() -> None:
    statuses = {step.key: CalibrationStepStatus.COMPLETED for step in CALIBRATION_STEPS}
    statuses["pressure_advance"] = CalibrationStepStatus.IN_PROGRESS
    assert ready_to_publish(statuses) is False


def test_repeating_earlier_step_marks_completed_dependants_for_review() -> None:
    changes = invalidated_statuses(
        [
            (1, CalibrationStepStatus.COMPLETED),
            (2, CalibrationStepStatus.COMPLETED),
            (3, CalibrationStepStatus.IN_PROGRESS),
            (4, CalibrationStepStatus.COMPLETED),
        ],
        repeated_order=1,
    )
    assert changes == {
        2: CalibrationStepStatus.NEEDS_REVIEW,
        4: CalibrationStepStatus.NEEDS_REVIEW,
    }


def test_dimensional_calibration_calculates_both_cura_expansions() -> None:
    result = calculate_dimensional_compensation(
        {
            "design_x_mm": "20",
            "measured_x_mm": "19.8",
            "design_y_mm": "20",
            "measured_y_mm": "19.9",
            "design_hole_mm": "10",
            "measured_hole_mm": "9.6",
        }
    )

    assert result.xy_offset == Decimal("0.075")
    assert result.hole_xy_offset == Decimal("0.2")
    assert result.axis_warning is False


def test_dimensional_calibration_warns_when_axis_corrections_diverge() -> None:
    result = calculate_dimensional_compensation(
        {
            "design_x_mm": "20",
            "measured_x_mm": "19.6",
            "design_y_mm": "20",
            "measured_y_mm": "20",
            "design_hole_mm": "10",
            "measured_hole_mm": "10",
        }
    )

    assert result.axis_difference == Decimal("0.2")
    assert result.axis_warning is True
