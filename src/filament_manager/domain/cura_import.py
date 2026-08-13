"""Safe conversion of bounded Cura material settings into canonical values."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from uuid import UUID

from filament_manager.domain.cura_material_settings import CURA_EXTENSION_SETTING_KEYS


def _decimal(
    settings: Mapping[str, object],
    *keys: str,
    required: bool = False,
) -> Decimal | None:
    value = next((settings[key] for key in keys if settings.get(key) not in {None, ""}), None)
    if value is None:
        if required:
            raise ValueError(f"Cura material is missing required setting {keys[0]}")
        return None
    if isinstance(value, bool):
        raise ValueError(f"Cura material setting {keys[0]} must be numeric")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Cura material setting {keys[0]} must be a decimal value") from exc
    if not parsed.is_finite():
        raise ValueError(f"Cura material setting {keys[0]} must be finite")
    return parsed


def _boolean(settings: Mapping[str, object], key: str, *, default: bool) -> bool:
    value = settings.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if value in {"True", "true"}:
        return True
    if value in {"False", "false"}:
        return False
    raise ValueError(f"Cura material setting {key} must be a boolean")


def material_settings_from_cura(
    settings: Mapping[str, object],
    *,
    filament_density_g_cm3: Decimal,
    preferred_build_plate_surface_id: UUID | None,
) -> dict[str, object]:
    """Convert approved Cura keys into a complete canonical settings snapshot."""

    cooling_max = _decimal(settings, "cool_fan_speed_max", "cool_fan_speed")
    if cooling_max is None:
        cooling_max = Decimal("100")
    cooling_min = _decimal(settings, "cool_fan_speed_min")
    if cooling_min is None:
        cooling_min = cooling_max
    flow_percent = _decimal(settings, "material_flow")
    if flow_percent is None:
        flow_percent = Decimal("100")
    extensions = {key: value for key, value in settings.items() if key in CURA_EXTENSION_SETTING_KEYS}
    return {
        "chamber_temp_c": _decimal(settings, "build_volume_temperature"),
        "extruder_temp_c": _decimal(
            settings,
            "material_print_temperature",
            "default_material_print_temperature",
            required=True,
        ),
        "bed_temp_c": _decimal(
            settings,
            "material_bed_temperature",
            "default_material_bed_temperature",
            required=True,
        ),
        "flow_percent": flow_percent,
        "print_speed_mm_s": _decimal(settings, "speed_print"),
        "outer_wall_speed_mm_s": _decimal(settings, "speed_wall_0"),
        "inner_wall_speed_mm_s": _decimal(settings, "speed_wall_x"),
        "infill_speed_mm_s": _decimal(settings, "speed_infill"),
        "top_bottom_speed_mm_s": _decimal(settings, "speed_topbottom"),
        "initial_layer_speed_mm_s": _decimal(settings, "speed_print_layer_0", "speed_layer_0"),
        "travel_speed_mm_s": _decimal(settings, "speed_travel"),
        "support_speed_mm_s": _decimal(settings, "speed_support"),
        "retraction_distance_mm": _decimal(settings, "retraction_amount"),
        "retraction_speed_mm_s": _decimal(settings, "retraction_speed"),
        "cooling_enabled": _boolean(settings, "cool_fan_enabled", default=True),
        "cooling_min_percent": cooling_min,
        "cooling_max_percent": cooling_max,
        "support_overhang_angle_deg": _decimal(settings, "support_angle"),
        "tree_max_branch_angle_deg": None,
        "pressure_advance": _decimal(settings, "klipper_pressure_advance_factor"),
        "filament_density_g_cm3": filament_density_g_cm3,
        "preferred_build_plate_surface_id": preferred_build_plate_surface_id,
        "cura_extensions": extensions,
    }


def cura_setting_maps_equal(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    """Compare emitted Cura settings semantically without float conversion."""

    if set(left) != set(right):
        return False
    for key in left:
        left_value = left[key]
        right_value = right[key]
        if left_value == right_value:
            continue
        if isinstance(left_value, bool) or isinstance(right_value, bool):
            return False
        try:
            if Decimal(str(left_value)) == Decimal(str(right_value)):
                continue
        except (InvalidOperation, ValueError):
            pass
        return False
    return True
