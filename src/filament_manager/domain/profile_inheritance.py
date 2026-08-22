"""Sparse material-profile inheritance and resolved-snapshot helpers."""

from __future__ import annotations

import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING
from uuid import UUID

from filament_manager.domain.cura_material_settings import (
    CURA_EXTENSION_SETTING_KEYS,
    CURA_TEMPLATE_ONLY_SETTING_KEYS,
)

if TYPE_CHECKING:
    from filament_manager.models.inventory import MaterialProfile


PROFILE_SETTING_KEYS = (
    "chamber_temp_c",
    "extruder_temp_c",
    "bed_temp_c",
    "flow_percent",
    "print_speed_mm_s",
    "outer_wall_speed_mm_s",
    "inner_wall_speed_mm_s",
    "infill_speed_mm_s",
    "top_bottom_speed_mm_s",
    "initial_layer_speed_mm_s",
    "travel_speed_mm_s",
    "support_speed_mm_s",
    "retraction_distance_mm",
    "retraction_speed_mm_s",
    "retraction_prime_speed_mm_s",
    "cooling_enabled",
    "cooling_min_percent",
    "cooling_max_percent",
    "support_overhang_angle_deg",
    "tree_max_branch_angle_deg",
    "pressure_advance",
    "ironing_enabled",
    "ironing_flow_percent",
    "ironing_speed_mm_s",
    "ironing_line_spacing_mm",
    "filament_density_g_cm3",
    "preferred_build_plate_surface_id",
)

DECIMAL_SETTING_KEYS = frozenset(
    key
    for key in PROFILE_SETTING_KEYS
    if key not in {"cooling_enabled", "ironing_enabled", "preferred_build_plate_surface_id"}
)
NUMERIC_TEXT = re.compile(r"^-?\d+(?:\.\d+)?$")
TEMPLATE_ONLY_PROFILE_SETTING_KEYS = frozenset(
    {
        "print_speed_mm_s",
        "outer_wall_speed_mm_s",
        "inner_wall_speed_mm_s",
        "infill_speed_mm_s",
        "top_bottom_speed_mm_s",
        "initial_layer_speed_mm_s",
        "travel_speed_mm_s",
        "support_speed_mm_s",
        "cooling_enabled",
        "cooling_min_percent",
        "cooling_max_percent",
    }
)
TEMPLATE_ONLY_CURA_EXTENSION_KEYS = CURA_TEMPLATE_ONLY_SETTING_KEYS & CURA_EXTENSION_SETTING_KEYS


def _plain_value(value: object) -> object:
    """Return a JSON-compatible stable scalar without binary floating point."""

    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    return value


def _equivalent(left: object, right: object) -> bool:
    """Compare decimal text semantically while retaining exact non-numeric text."""

    left = _plain_value(left)
    right = _plain_value(right)
    if left == right:
        return True
    if isinstance(left, str) and isinstance(right, str):
        if NUMERIC_TEXT.fullmatch(left) and NUMERIC_TEXT.fullmatch(right):
            try:
                return Decimal(left) == Decimal(right)
            except InvalidOperation:
                return False
    return False


def normalize_settings(settings: dict[str, object]) -> dict[str, object]:
    """Return the complete bounded settings shape used by inheritance."""

    normalized = {key: _plain_value(settings.get(key)) for key in PROFILE_SETTING_KEYS}
    extensions = settings.get("cura_extensions", {})
    normalized["cura_extensions"] = {
        str(key): _plain_value(value)
        for key, value in (extensions.items() if isinstance(extensions, dict) else [])
        if str(key) in CURA_EXTENSION_SETTING_KEYS
    }
    return normalized


def profile_overrides_without_template_only(
    overrides: dict[str, object],
) -> dict[str, object]:
    """Remove settings that are owned exclusively by the linked template."""

    filtered = {
        key: deepcopy(value)
        for key, value in overrides.items()
        if key not in TEMPLATE_ONLY_PROFILE_SETTING_KEYS and key != "cura_extensions"
    }
    extensions = overrides.get("cura_extensions")
    if isinstance(extensions, dict):
        filtered_extensions = {
            str(key): deepcopy(value)
            for key, value in extensions.items()
            if str(key) not in TEMPLATE_ONLY_CURA_EXTENSION_KEYS
        }
        if filtered_extensions:
            filtered["cura_extensions"] = filtered_extensions
    return filtered


def resolve_profile_settings(
    base_settings: dict[str, object],
    overrides: dict[str, object],
) -> dict[str, object]:
    """Resolve one complete effective snapshot from a template and sparse overrides."""

    overrides = profile_overrides_without_template_only(overrides)
    resolved = normalize_settings(base_settings)
    for key in PROFILE_SETTING_KEYS:
        if key in overrides:
            resolved[key] = _plain_value(overrides[key])
    raw_base_extensions = resolved.get("cura_extensions", {})
    base_extensions = dict(raw_base_extensions) if isinstance(raw_base_extensions, dict) else {}
    override_extensions = overrides.get("cura_extensions", {})
    if isinstance(override_extensions, dict):
        for key, value in override_extensions.items():
            if value is None:
                base_extensions.pop(str(key), None)
            else:
                base_extensions[str(key)] = _plain_value(value)
    resolved["cura_extensions"] = base_extensions
    return resolved


def resolve_profile_settings_for_template_update(
    new_base_settings: dict[str, object],
    current_settings: dict[str, object],
    overrides: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Resolve a template update after removing template-owned overrides."""

    adjusted_overrides = profile_overrides_without_template_only(overrides)
    return resolve_profile_settings(new_base_settings, adjusted_overrides), adjusted_overrides


def sparse_profile_overrides(
    base_settings: dict[str, object],
    desired_settings: dict[str, object],
) -> dict[str, object]:
    """Return only values that semantically differ from the selected template."""

    base = normalize_settings(base_settings)
    desired = normalize_settings(desired_settings)
    overrides: dict[str, object] = {}
    for key in PROFILE_SETTING_KEYS:
        if key in TEMPLATE_ONLY_PROFILE_SETTING_KEYS:
            continue
        if not _equivalent(base.get(key), desired.get(key)):
            overrides[key] = desired.get(key)

    base_extensions = base.get("cura_extensions", {})
    desired_extensions = desired.get("cura_extensions", {})
    assert isinstance(base_extensions, dict)
    assert isinstance(desired_extensions, dict)
    extension_overrides: dict[str, object] = {}
    for key in sorted(set(base_extensions) | set(desired_extensions)):
        if key in TEMPLATE_ONLY_CURA_EXTENSION_KEYS:
            continue
        base_value = base_extensions.get(key)
        desired_value = desired_extensions.get(key)
        if not _equivalent(base_value, desired_value):
            extension_overrides[key] = desired_value if key in desired_extensions else None
    if extension_overrides:
        overrides["cura_extensions"] = extension_overrides
    return overrides


def settings_snapshot_from_profile(profile: MaterialProfile) -> dict[str, object]:
    """Read the complete resolved snapshot cached on one profile revision."""

    values = {key: _plain_value(getattr(profile, key)) for key in PROFILE_SETTING_KEYS}
    values["cura_extensions"] = deepcopy(profile.cura_extensions)
    return normalize_settings(values)


def profile_columns_from_settings(settings: dict[str, object]) -> dict[str, object]:
    """Convert one validated effective snapshot into typed ORM column values."""

    normalized = normalize_settings(settings)
    columns: dict[str, object] = {}
    for key in PROFILE_SETTING_KEYS:
        value = normalized[key]
        if key in DECIMAL_SETTING_KEYS:
            columns[key] = Decimal(str(value)) if value is not None else None
        elif key == "preferred_build_plate_surface_id":
            columns[key] = UUID(str(value)) if value is not None else None
        elif key == "cooling_enabled":
            columns[key] = bool(value)
        elif key == "ironing_enabled":
            columns[key] = bool(value) if value is not None else None
        else:
            columns[key] = value
    columns["cura_extensions"] = deepcopy(normalized["cura_extensions"])
    return columns


def override_setting_keys(overrides: dict[str, object]) -> set[str]:
    """Return user-facing setting keys customized by one profile revision."""

    filtered = profile_overrides_without_template_only(overrides)
    keys = {key for key in filtered if key != "cura_extensions"}
    extensions = filtered.get("cura_extensions")
    if isinstance(extensions, dict):
        keys.update(extensions)
    return keys
