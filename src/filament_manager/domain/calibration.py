"""Ordered calibration workflow and dependency invalidation rules."""

from dataclasses import dataclass

from filament_manager.models.enums import CalibrationStepStatus


@dataclass(frozen=True)
class StepDefinition:
    """One immutable calibration step definition."""

    order: int
    key: str
    name: str
    required: bool
    profile_outputs: tuple[str, ...]


CALIBRATION_STEPS: tuple[StepDefinition, ...] = (
    StepDefinition(1, "temperature", "Temperature Tower", True, ("extruder_temp_c",)),
    StepDefinition(2, "flow", "Flow Rate Tower", True, ("flow_percent",)),
    StepDefinition(3, "pressure_advance", "Pressure Advance Square Tower", True, ("pressure_advance",)),
    StepDefinition(
        4,
        "retraction",
        "Retraction Tower",
        True,
        ("retraction_distance_mm", "retraction_speed_mm_s"),
    ),
    StepDefinition(
        5,
        "overhang",
        "Overhang Test",
        True,
        ("support_overhang_angle_deg", "tree_max_branch_angle_deg"),
    ),
    StepDefinition(
        6,
        "ironing",
        "Ironing Test",
        False,
        (
            "ironing_enabled",
            "ironing_flow_percent",
            "ironing_speed_mm_s",
            "ironing_line_spacing_mm",
        ),
    ),
)


def invalidated_statuses(
    steps: list[tuple[int, CalibrationStepStatus]], repeated_order: int
) -> dict[int, CalibrationStepStatus]:
    """Return downstream completed steps that must move to needs-review."""

    return {
        order: CalibrationStepStatus.NEEDS_REVIEW
        for order, status in steps
        if order > repeated_order and status == CalibrationStepStatus.COMPLETED
    }


def ready_to_publish(step_statuses: dict[str, CalibrationStepStatus]) -> bool:
    """Return whether every mandatory calibration step is complete."""

    return all(
        not definition.required or step_statuses.get(definition.key) == CalibrationStepStatus.COMPLETED
        for definition in CALIBRATION_STEPS
    )
