"""Template-only descriptive filament care choices, never printer commands."""

from typing import Literal

MoistureSensitivity = Literal[
    "low", "low-moderate", "moderate", "high-moderate", "high", "very high", "extremely high"
]
DryingTimeHours = Literal["4-6", "6", "6-8", "4-8", "8-12", "10-12", "12", "12+"]
FILAMENT_CARE_KEYS = frozenset({"drying_temp_c", "drying_time_hours", "moisture_sensitivity"})
