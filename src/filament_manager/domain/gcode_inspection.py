"""Bounded Cura G-code metadata extraction and canonical profile comparison."""

from __future__ import annotations

import configparser
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_GCODE_TEXT_LENGTH = 1_100_000
MAX_SETTING_VALUE_LENGTH = 500
MAX_CAPTURED_CURA_SETTINGS = 4_096
MAX_CURA_EXTRUDERS = 8
SETTING_LINE_PREFIX = ";SETTING_3 "
DECIMAL_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
SETTING_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,95}")
SENSITIVE_SETTING_KEY_PATTERN = re.compile(
    r"(^|_)(?:api_?key|credential|directory|endpoint|file|host|hostname|password|passwd|path|secret|token|url|uri)(?:_|$)"
)
UNSAFE_SETTING_VALUE_PATTERN = re.compile(r"(?:https?://|\x00)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class InspectionResult:
    """Sanitized extracted fields and semantic profile mismatches."""

    extracted: dict[str, object]
    mismatches: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    cura_settings: dict[str, object]


def _bounded_text(value: object, maximum: int = 255) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.replace("\x00", "").split())
    return normalized[:maximum] or None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def _unavailable_cura_settings(reason: str) -> dict[str, object]:
    """Return a stable, non-sensitive reason for unavailable Cura settings."""

    return {
        "available": False,
        "reason": reason,
        "global": None,
        "extruders": [],
        "setting_count": 0,
        "filtered_count": 0,
        "truncated": False,
    }


def _safe_cura_scope(
    payload: str,
    *,
    remaining: int,
    fallback_position: int | None,
) -> tuple[dict[str, object] | None, dict[str, str], int, int, bool]:
    """Parse one bounded Cura INI scope while retaining inert setting text."""

    if len(payload) > MAX_GCODE_TEXT_LENGTH:
        return None, {}, 0, 0, True
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(payload)
    except configparser.Error:
        return None, {}, 0, 0, False

    settings: dict[str, str] = {}
    filtered_count = 0
    truncated = False
    if parser.has_section("values"):
        for key, raw_value in parser.items("values"):
            value = raw_value.strip()
            if (
                SETTING_KEY_PATTERN.fullmatch(key) is None
                or len(value) > MAX_SETTING_VALUE_LENGTH
                or SENSITIVE_SETTING_KEY_PATTERN.search(key) is not None
                or UNSAFE_SETTING_VALUE_PATTERN.search(value) is not None
            ):
                filtered_count += 1
                continue
            if len(settings) >= remaining:
                truncated = True
                break
            settings[key] = value

    scope: dict[str, object] = {"settings": settings}
    if parser.has_section("general"):
        for key in ("name", "definition"):
            if parser.has_option("general", key):
                bounded_value = _bounded_text(parser.get("general", key), MAX_SETTING_VALUE_LENGTH)
                if bounded_value is not None:
                    scope[key] = bounded_value
    if fallback_position is not None:
        position: object = fallback_position
        if parser.has_section("metadata") and parser.has_option("metadata", "position"):
            parsed_position = _bounded_text(parser.get("metadata", "position"), 16)
            if parsed_position is not None:
                position = parsed_position
        scope["position"] = position
    return scope, settings, len(settings), filtered_count, truncated


def _parse_cura_setting_payload(tail: str) -> tuple[dict[str, str], dict[str, object]]:
    """Decode Cura's bounded SETTING_3 JSON/INI payload without evaluation."""

    fragments = [
        line[len(SETTING_LINE_PREFIX) :] for line in tail.splitlines() if line.startswith(SETTING_LINE_PREFIX)
    ]
    if not fragments:
        return {}, _unavailable_cura_settings("not_embedded")
    serialized = "".join(fragments)
    if len(serialized) > MAX_GCODE_TEXT_LENGTH:
        return {}, _unavailable_cura_settings("payload_too_large")
    try:
        document = json.loads(serialized)
    except json.JSONDecodeError:
        return {}, _unavailable_cura_settings("invalid_payload")
    if not isinstance(document, dict):
        return {}, _unavailable_cura_settings("invalid_payload")

    merged_settings: dict[str, str] = {}
    global_scope: dict[str, object] | None = None
    extruder_scopes: list[dict[str, object]] = []
    setting_count = 0
    filtered_count = 0
    truncated = False
    global_quality = document.get("global_quality")
    if isinstance(global_quality, str):
        scope, settings, count, filtered, scope_truncated = _safe_cura_scope(
            global_quality,
            remaining=MAX_CAPTURED_CURA_SETTINGS - setting_count,
            fallback_position=None,
        )
        global_scope = scope
        merged_settings.update(settings)
        setting_count += count
        filtered_count += filtered
        truncated = truncated or scope_truncated
    extruder_quality = document.get("extruder_quality")
    if isinstance(extruder_quality, list):
        string_payloads = [item for item in extruder_quality if isinstance(item, str)]
        if len(string_payloads) > MAX_CURA_EXTRUDERS:
            truncated = True
        for index, payload in enumerate(string_payloads[:MAX_CURA_EXTRUDERS]):
            scope, settings, count, filtered, scope_truncated = _safe_cura_scope(
                payload,
                remaining=max(0, MAX_CAPTURED_CURA_SETTINGS - setting_count),
                fallback_position=index,
            )
            if scope is not None:
                extruder_scopes.append(scope)
            merged_settings.update(settings)
            setting_count += count
            filtered_count += filtered
            truncated = truncated or scope_truncated
    if global_scope is not None:
        for key in ("name", "definition"):
            value = global_scope.get(key)
            if isinstance(value, str):
                merged_settings[f"quality_{key}"] = value
    return merged_settings, {
        "available": global_scope is not None or bool(extruder_scopes),
        "reason": None if global_scope is not None or extruder_scopes else "invalid_payload",
        "global": global_scope,
        "extruders": extruder_scopes,
        "setting_count": setting_count,
        "filtered_count": filtered_count,
        "truncated": truncated,
    }


def _extract_gcode_metadata(
    metadata: dict[str, Any],
    header: str,
    settings: dict[str, str],
) -> dict[str, object]:
    """Extract supported fields from pre-bounded and pre-parsed evidence."""

    extracted: dict[str, object] = {}

    text_fields = {
        "slicer": metadata.get("slicer"),
        "slicer_version": metadata.get("slicer_version"),
        "material_name": metadata.get("filament_name"),
        "material_type": metadata.get("filament_type"),
        "machine_name": settings.get("machine_name") or settings.get("quality_definition"),
        "cura_quality_profile": settings.get("quality_name"),
    }
    generated_version = _first_match(header, r"^;Generated with Cura_SteamEngine\s+([^\r\n]+)$")
    if generated_version:
        text_fields["slicer"] = "Cura"
        text_fields["slicer_version"] = generated_version
    material_guid = _first_match(header, r"\bMATERIAL_GUID=([0-9a-fA-F-]{36})\b")
    if material_guid:
        text_fields["material_guid"] = material_guid.lower()
    for key, value in text_fields.items():
        bounded = _bounded_text(value)
        if bounded is not None:
            extracted[key] = bounded

    decimal_sources: dict[str, object] = {
        "estimated_duration_seconds": metadata.get("estimated_time")
        or _first_match(header, r"^;TIME:([0-9.]+)$"),
        "predicted_filament_length_mm": metadata.get("filament_total"),
        "predicted_filament_weight_g": metadata.get("filament_weight_total"),
        "layer_height_mm": metadata.get("layer_height")
        or settings.get("layer_height")
        or _first_match(header, r"^;Layer height:\s*([0-9.]+)$"),
        "line_width_mm": settings.get("line_width") or settings.get("wall_line_width"),
        "nozzle_diameter_mm": metadata.get("nozzle_diameter") or settings.get("machine_nozzle_size"),
        "extruder_temp_c": metadata.get("first_layer_extr_temp")
        or settings.get("material_print_temperature")
        or _first_match(header, r"\bEXTRUDER_TEMP=([0-9.]+)\b")
        or _first_match(header, r"^M10[49]\s+S([0-9.]+)\b"),
        # Cura's SETTING_3 document describes saved quality-layer values, not a
        # trustworthy resolved material value. The managed start boundary is
        # therefore the only supported regular-temperature evidence. Initial
        # evidence remains separate and prefers the exact managed boundary or
        # an actual first-layer heating value.
        "bed_temp_c": _first_match(header, r"\bREGULAR_BED_TEMP=([0-9.]+)\b"),
        "initial_bed_temp_c": _first_match(header, r"\bBED_TEMP=([0-9.]+)\b")
        or metadata.get("first_layer_bed_temp")
        or _first_match(header, r"^M1(?:40|90)\s+S([0-9.]+)\b")
        or settings.get("material_bed_temperature_layer_0"),
        "chamber_temp_c": metadata.get("chamber_temp")
        or settings.get("build_volume_temperature")
        or _first_match(header, r"\bCHAMBER_TEMP=([0-9.]+)\b"),
        "print_speed_mm_s": settings.get("speed_print"),
        "flow_percent": settings.get("material_flow"),
        "retraction_distance_mm": settings.get("retraction_amount"),
        "retraction_speed_mm_s": settings.get("retraction_retract_speed") or settings.get("retraction_speed"),
        "retraction_prime_speed_mm_s": settings.get("retraction_prime_speed")
        or settings.get("retraction_retract_speed")
        or settings.get("retraction_speed"),
        "pressure_advance": settings.get("pressure_advance")
        or _first_match(header, r"^SET_PRESSURE_ADVANCE\s+[^\r\n]*ADVANCE=([0-9.]+)\b"),
    }
    if decimal_sources["predicted_filament_length_mm"] is None:
        filament_m = _first_match(header, r"^;Filament used:\s*([0-9.]+)m\s*$")
        if filament_m:
            parsed_m = _decimal(filament_m)
            decimal_sources["predicted_filament_length_mm"] = parsed_m * 1000 if parsed_m else None
    for key, value in decimal_sources.items():
        parsed = _decimal(value)
        if parsed is not None:
            extracted[key] = format(parsed, "f")

    support_enabled = settings.get("support_enable")
    if support_enabled is not None:
        extracted["support_configuration"] = {
            "enabled": support_enabled.casefold() == "true",
            "structure": _bounded_text(settings.get("support_structure"), 96),
            "placement": _bounded_text(settings.get("support_type"), 96),
        }
    return extracted


def extract_gcode_metadata(metadata: dict[str, Any], header: str, tail: str) -> dict[str, object]:
    """Extract supported Moonraker and Cura fields from bounded untrusted input."""

    bounded_header = header[:MAX_GCODE_TEXT_LENGTH]
    settings, _ = _parse_cura_setting_payload(tail[-MAX_GCODE_TEXT_LENGTH:])
    return _extract_gcode_metadata(metadata, bounded_header, settings)


def inspect_gcode(
    metadata: dict[str, Any],
    header: str,
    tail: str,
    *,
    expected_profile: dict[str, object] | None,
    expected_material_guid: str | None,
    expected_machine_name: str | None,
) -> InspectionResult:
    """Compare extracted G-code settings with one immutable profile snapshot."""

    bounded_header = header[:MAX_GCODE_TEXT_LENGTH]
    settings, cura_settings = _parse_cura_setting_payload(tail[-MAX_GCODE_TEXT_LENGTH:])
    extracted = _extract_gcode_metadata(metadata, bounded_header, settings)
    mismatches: list[dict[str, object]] = []
    warnings: list[str] = []
    if expected_profile is None:
        warnings.append("No exact managed material profile could be resolved for this G-code file.")
        return InspectionResult(extracted, tuple(mismatches), tuple(warnings), cura_settings)

    comparisons = (
        ("nozzle_diameter_mm", "nozzle diameter", Decimal("0.001")),
        ("extruder_temp_c", "printing temperature", Decimal("0.5")),
        ("bed_temp_c", "build plate temperature", Decimal("0.5")),
        (
            "initial_bed_temp_c",
            "initial layer build plate temperature",
            Decimal("0.5"),
        ),
        ("chamber_temp_c", "chamber temperature", Decimal("0.5")),
        ("print_speed_mm_s", "print speed", Decimal("0.01")),
        ("flow_percent", "flow", Decimal("0.01")),
        ("retraction_distance_mm", "retraction distance", Decimal("0.001")),
        ("retraction_speed_mm_s", "retraction retract speed", Decimal("0.01")),
        ("retraction_prime_speed_mm_s", "retraction prime speed", Decimal("0.01")),
        ("pressure_advance", "pressure advance", Decimal("0.0001")),
    )
    for key, label, tolerance in comparisons:
        actual = _decimal(extracted.get(key))
        expected = _decimal(expected_profile.get(key))
        if actual is None or expected is None or abs(actual - expected) <= tolerance:
            continue
        mismatches.append(
            {
                "field": key,
                "label": label,
                "gcode_value": format(actual, "f"),
                "profile_value": format(expected, "f"),
            }
        )
    actual_guid = extracted.get("material_guid")
    if expected_material_guid and actual_guid and actual_guid != expected_material_guid:
        mismatches.append(
            {
                "field": "material_guid",
                "label": "managed material",
                "gcode_value": str(actual_guid),
                "profile_value": expected_material_guid,
            }
        )
    actual_machine = extracted.get("machine_name")
    if (
        expected_machine_name
        and actual_machine
        and str(actual_machine).casefold() != expected_machine_name.casefold()
    ):
        mismatches.append(
            {
                "field": "machine_name",
                "label": "machine",
                "gcode_value": str(actual_machine),
                "profile_value": expected_machine_name,
            }
        )
    for key in ("slicer", "layer_height_mm", "predicted_filament_length_mm"):
        if key not in extracted:
            warnings.append(f"G-code metadata did not provide {key.replace('_', ' ')}.")
    return InspectionResult(extracted, tuple(mismatches), tuple(warnings), cura_settings)
