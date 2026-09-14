"""Stable optimistic-concurrency tokens for operator-editable printer settings."""

import hashlib
import json

PRINTER_SETTING_FIELDS = (
    "name",
    "manufacturer",
    "model",
    "kinematics",
    "extruder_type",
    "notes",
    "nozzle_diameter_mm",
    "nozzle_material",
    "active_nozzle_id",
    "build_volume",
    "heated_chamber",
    "max_extruder_temp_c",
    "max_bed_temp_c",
    "extruder_count",
    "power_device",
    "tool_routines_verified",
)


def printer_settings_token(printer: object) -> str:
    """Ignore telemetry churn while detecting any concurrent editable-field change."""
    values = {key: getattr(printer, key, None) for key in PRINTER_SETTING_FIELDS}
    encoded = json.dumps(values, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
