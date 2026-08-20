"""Approved Cura Material Settings catalog and profile-to-Cura mapping."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class CuraMaterialSetting:
    """One setting exposed by the operator's Cura Material Settings plugin."""

    key: str
    label: str
    value_type: Literal["boolean", "number", "string"]
    unit: str | None = None
    editable: bool = True


def _number(key: str, label: str, unit: str | None = None) -> CuraMaterialSetting:
    return CuraMaterialSetting(key, label, "number", unit)


def _boolean(key: str, label: str) -> CuraMaterialSetting:
    return CuraMaterialSetting(key, label, "boolean")


# This order mirrors the active Cura 5.13 Material Settings plugin configuration supplied
# by the operator. Brand and material type are derived from the canonical filament product.
CURA_MATERIAL_SETTINGS: tuple[CuraMaterialSetting, ...] = (
    _number("speed_layer_0", "Initial Layer Speed", "mm/s"),
    _boolean("retraction_enable", "Enable Retraction"),
    _number("material_print_temperature", "Printing Temperature", "°C"),
    _number("material_bed_temperature", "Build Plate Temperature", "°C"),
    _number("speed_wall_x", "Inner Wall Speed", "mm/s"),
    CuraMaterialSetting("material_type", "Material Type", "string", editable=False),
    _number("xy_offset_layer_0", "Initial Layer Horizontal Expansion", "mm"),
    _number("speed_infill", "Infill Speed", "mm/s"),
    _number("retraction_retract_speed", "Retraction Retract Speed", "mm/s"),
    _number("retraction_amount", "Retraction Distance", "mm"),
    _number("hole_xy_offset_max_diameter", "Hole Horizontal Expansion Max Diameter", "mm"),
    _number("cool_fan_speed_min", "Regular Fan Speed", "%"),
    _number("support_angle", "Support Overhang Angle", "°"),
    _number("material_flow", "Flow", "%"),
    _number("speed_roofing", "Top Surface Skin Speed", "mm/s"),
    _boolean("cool_fan_enabled", "Enable Print Cooling"),
    _number("speed_wall_0", "Outer Wall Speed", "mm/s"),
    _number("speed_topbottom", "Top/Bottom Speed", "mm/s"),
    _number("default_material_print_temperature", "Default Printing Temperature", "°C"),
    _number("speed_travel_layer_0", "Initial Layer Travel Speed", "mm/s"),
    _number("retraction_prime_speed", "Retraction Prime Speed", "mm/s"),
    _number("speed_print", "Print Speed", "mm/s"),
    _boolean("limit_support_retractions", "Limit Support Retractions"),
    _number("infill_material_flow", "Infill Flow", "%"),
    _number("support_material_flow", "Support Flow", "%"),
    _number("speed_travel", "Travel Speed", "mm/s"),
    _number("klipper_pressure_advance_factor", "Klipper Pressure Advance", "s"),
    _boolean("klipper_smooth_time_enable", "Enable Klipper Smooth Time"),
    _number("speed_print_layer_0", "Initial Layer Print Speed", "mm/s"),
    _number("klipper_smooth_time_factor", "Klipper Smooth Time", "s"),
    _number("material_print_temperature_layer_0", "Initial Printing Temperature", "°C"),
    _number("material_standby_temperature", "Standby Temperature", "°C"),
    _number("cool_fan_speed", "Fan Speed", "%"),
    CuraMaterialSetting("material_brand", "Material Brand", "string", editable=False),
    _number("cool_fan_speed_max", "Maximum Fan Speed", "%"),
    _number("cool_fan_full_layer", "Regular Fan Speed at Layer"),
    _number("material_flow_layer_0", "Initial Layer Flow", "%"),
    _number("xy_offset", "Horizontal Expansion", "mm"),
    _number("material_initial_print_temperature", "Initial Printing Temperature", "°C"),
    _number("build_volume_temperature", "Build Volume Temperature", "°C"),
    _number("skirt_brim_speed", "Skirt/Brim Speed", "mm/s"),
    _number("hole_xy_offset", "Hole Horizontal Expansion", "mm"),
    _number("cool_min_layer_time", "Minimum Layer Time", "s"),
    _number("speed_support", "Support Speed", "mm/s"),
    _number("material_final_print_temperature", "Final Printing Temperature", "°C"),
    _number("default_material_bed_temperature", "Default Build Plate Temperature", "°C"),
    _number("material_bed_temperature_layer_0", "Initial Build Plate Temperature", "°C"),
    _number("retraction_min_travel", "Retraction Minimum Travel", "mm"),
    _number("roofing_material_flow", "Top Surface Skin Flow", "%"),
    _number("skirt_brim_material_flow", "Skirt/Brim Flow", "%"),
    _number("cool_min_layer_time_fan_speed_max", "Minimum Layer Time at Maximum Fan", "s"),
    CuraMaterialSetting(
        "retraction_speed",
        "Legacy Retraction Speed Alias",
        "number",
        "mm/s",
        editable=False,
    ),
    _boolean("retract_at_layer_change", "Retract at Layer Change"),
    _number("cool_min_speed", "Minimum Speed", "mm/s"),
    _number("speed_wall", "Wall Speed", "mm/s"),
    CuraMaterialSetting("cool_fan_speed_0", "Initial Fan Speed", "number", "%", editable=False),
)

CURA_MATERIAL_SETTING_KEYS = frozenset(setting.key for setting in CURA_MATERIAL_SETTINGS)
CURA_EDITABLE_SETTING_KEYS = frozenset(setting.key for setting in CURA_MATERIAL_SETTINGS if setting.editable)

# Cura exposes a few child/alias keys that duplicate one canonical material value in
# Filament Manager.  Continue accepting legacy snapshots containing these keys, but
# never present or persist them as independent profile customizations.  Emission below
# deliberately writes the canonical value to every Cura alias so the generated material
# remains deterministic without showing operators overlapping controls.
CURA_PROFILE_ALIAS_SETTING_KEYS = frozenset(
    {
        "cool_fan_speed_max",
        "retraction_speed",
    }
)

# These values live in typed canonical columns. The remaining approved settings are stored
# in cura_extensions so arbitrary Cura keys can never be injected into workstation files.
CURA_TYPED_SETTING_KEYS = frozenset(
    {
        "build_volume_temperature",
        "cool_fan_enabled",
        "cool_fan_speed",
        "cool_fan_speed_min",
        "default_material_bed_temperature",
        "default_material_print_temperature",
        "klipper_pressure_advance_factor",
        "material_bed_temperature",
        "material_flow",
        "material_print_temperature",
        "retraction_amount",
        "retraction_prime_speed",
        "retraction_retract_speed",
        "retraction_speed",
        "speed_infill",
        "speed_layer_0",
        "speed_print",
        "speed_print_layer_0",
        "speed_support",
        "speed_topbottom",
        "speed_travel",
        "speed_wall_0",
        "speed_wall_x",
        "support_angle",
    }
)
CURA_EXTENSION_SETTING_KEYS = CURA_EDITABLE_SETTING_KEYS - CURA_TYPED_SETTING_KEYS


class MaterialProfileValues(Protocol):
    """Typed profile fields needed to construct a Cura material settings map."""

    chamber_temp_c: Decimal | None
    extruder_temp_c: Decimal
    bed_temp_c: Decimal
    flow_percent: Decimal
    print_speed_mm_s: Decimal | None
    outer_wall_speed_mm_s: Decimal | None
    inner_wall_speed_mm_s: Decimal | None
    infill_speed_mm_s: Decimal | None
    top_bottom_speed_mm_s: Decimal | None
    initial_layer_speed_mm_s: Decimal | None
    travel_speed_mm_s: Decimal | None
    support_speed_mm_s: Decimal | None
    retraction_distance_mm: Decimal | None
    retraction_speed_mm_s: Decimal | None
    retraction_prime_speed_mm_s: Decimal | None
    cooling_enabled: bool
    cooling_min_percent: Decimal
    cooling_max_percent: Decimal
    support_overhang_angle_deg: Decimal | None
    pressure_advance: Decimal | None
    cura_extensions: dict[str, object]


def _decimal(value: Decimal | None) -> str | None:
    """Serialize decimal settings without binary floating-point conversion."""

    return format(value, "f") if value is not None else None


def cura_settings_for_profile(profile: MaterialProfileValues) -> dict[str, object]:
    """Return the approved material-scoped Cura settings for one profile version."""

    settings = {
        key: value
        for key, value in profile.cura_extensions.items()
        if key in CURA_EXTENSION_SETTING_KEYS and value is not None
    }
    typed_values: dict[str, object | None] = {
        "build_volume_temperature": _decimal(profile.chamber_temp_c),
        "cool_fan_enabled": profile.cooling_enabled,
        "cool_fan_speed": _decimal(profile.cooling_max_percent),
        "cool_fan_speed_max": _decimal(profile.cooling_max_percent),
        "cool_fan_speed_min": _decimal(profile.cooling_min_percent),
        "default_material_bed_temperature": _decimal(profile.bed_temp_c),
        "default_material_print_temperature": _decimal(profile.extruder_temp_c),
        "klipper_pressure_advance_factor": _decimal(profile.pressure_advance),
        "material_bed_temperature": _decimal(profile.bed_temp_c),
        "material_flow": _decimal(profile.flow_percent),
        "material_print_temperature": _decimal(profile.extruder_temp_c),
        "retraction_amount": _decimal(profile.retraction_distance_mm),
        "retraction_prime_speed": _decimal(profile.retraction_prime_speed_mm_s),
        "retraction_retract_speed": _decimal(profile.retraction_speed_mm_s),
        "retraction_speed": _decimal(profile.retraction_speed_mm_s),
        "cool_fan_speed_0": "0",
        "speed_infill": _decimal(profile.infill_speed_mm_s),
        "speed_layer_0": _decimal(profile.initial_layer_speed_mm_s),
        "speed_print": _decimal(profile.print_speed_mm_s),
        "speed_print_layer_0": _decimal(profile.initial_layer_speed_mm_s),
        "speed_support": _decimal(profile.support_speed_mm_s),
        "speed_topbottom": _decimal(profile.top_bottom_speed_mm_s),
        "speed_travel": _decimal(profile.travel_speed_mm_s),
        "speed_wall_0": _decimal(profile.outer_wall_speed_mm_s),
        "speed_wall_x": _decimal(profile.inner_wall_speed_mm_s),
        "support_angle": _decimal(profile.support_overhang_angle_deg),
    }
    settings.update({key: value for key, value in typed_values.items() if value is not None})
    return settings


def cura_material_settings_catalog() -> list[dict[str, object]]:
    """Return the serializable ordered catalog used by the profile editor."""

    return [asdict(setting) for setting in CURA_MATERIAL_SETTINGS]
