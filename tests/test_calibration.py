"""Ordered six-step calibration policy tests."""

from filament_manager.domain.calibration import CALIBRATION_STEPS, invalidated_statuses, ready_to_publish
from filament_manager.models.enums import CalibrationStepStatus


def test_workflow_preserves_exact_six_steps() -> None:
    assert [(step.order, step.key, step.required) for step in CALIBRATION_STEPS] == [
        (1, "temperature", True),
        (2, "flow", True),
        (3, "pressure_advance", True),
        (4, "retraction", True),
        (5, "overhang", True),
        (6, "ironing", False),
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
