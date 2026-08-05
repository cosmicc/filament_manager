"""Deterministic Cura material and quality-change profile rendering."""

import configparser
import io
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .models import CuraInstallation, CuraMachine

MANAGED_START = "; FILAMENT MANAGER PRESSURE ADVANCE BEGIN"
MANAGED_END = "; FILAMENT MANAGER PRESSURE ADVANCE END"
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
GLOBAL_KEYS = {
    "speed_print",
    "speed_wall_0",
    "speed_wall_x",
    "speed_infill",
    "speed_topbottom",
    "speed_layer_0",
    "speed_travel",
    "speed_support",
    "bridge_wall_speed",
    "support_angle",
    "support_tree_angle",
    "ironing_enabled",
    "ironing_flow",
    "speed_ironing",
    "ironing_line_spacing",
}


class MachineMatchError(RuntimeError):
    """Raised when a profile cannot be safely mapped to one Cura machine."""


class CasePreservingConfigParser(configparser.ConfigParser):
    """Preserve Cura setting-key case while satisfying the typed parser contract."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


@dataclass(frozen=True)
class RenderedDeployment:
    """Rendered relative files and informational warnings for one installation."""

    files: dict[Path, bytes]
    machine: CuraMachine
    warnings: list[str]


def slug(value: str, *, maximum: int = 72) -> str:
    """Create a bounded portable filename fragment."""

    result = SLUG_PATTERN.sub("_", value.casefold()).strip("_")
    return (result or "profile")[:maximum]


def _normalized(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def match_machine(installation: CuraInstallation, printer: dict[str, Any]) -> CuraMachine:
    """Select one unambiguous machine using identity, name, and nozzle evidence."""

    expected_names = {_normalized(str(printer.get("name", ""))), _normalized(str(printer.get("code", "")))}
    expected_names.discard("")
    expected_nozzle = str(printer.get("nozzle_diameter_mm") or "").rstrip("0").rstrip(".")
    scored: list[tuple[int, CuraMachine]] = []
    for machine in installation.machines:
        identities = {_normalized(machine.machine_id), _normalized(machine.display_name)}
        score = 0
        if expected_names & identities:
            score += 100
        elif any(
            expected in identity or identity in expected
            for expected in expected_names
            for identity in identities
        ):
            score += 40
        machine_nozzle = (machine.nozzle_diameter_mm or "").rstrip("0").rstrip(".")
        if expected_nozzle and machine_nozzle == expected_nozzle:
            score += 20
        if score:
            scored.append((score, machine))
    if not scored:
        raise MachineMatchError(
            f"No Cura machine matches '{printer.get('name')}' with a "
            f"{printer.get('nozzle_diameter_mm')} mm nozzle."
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        raise MachineMatchError(f"More than one Cura machine matches '{printer.get('name')}'.")
    return scored[0][1]


def _material_xml(payload: dict[str, Any]) -> bytes:
    material = payload["material"]
    profile = payload["profile"]
    settings = profile["settings"]
    namespace = "http://www.ultimaker.com/material"
    cura_namespace = "http://www.ultimaker.com/cura"
    ET.register_namespace("", namespace)
    ET.register_namespace("cura", cura_namespace)
    root = ET.Element(f"{{{namespace}}}fdmmaterial", {"version": "1.3"})
    metadata = ET.SubElement(root, f"{{{namespace}}}metadata")
    name = ET.SubElement(metadata, f"{{{namespace}}}name")
    for key, value in (
        ("brand", material["brand"]),
        ("material", material["material_type"]),
        ("color", material["color_name"]),
        ("label", material.get("product_name") or material["color_name"]),
    ):
        ET.SubElement(name, f"{{{namespace}}}{key}").text = str(value)
    ET.SubElement(metadata, f"{{{namespace}}}version").text = str(profile["version"])
    ET.SubElement(metadata, f"{{{namespace}}}color_code").text = str(material["color_hex"])
    guid = uuid.uuid5(uuid.NAMESPACE_URL, f"filament-manager:{material['product_id']}")
    ET.SubElement(metadata, f"{{{namespace}}}GUID").text = str(guid)
    properties = ET.SubElement(root, f"{{{namespace}}}properties")
    ET.SubElement(properties, f"{{{namespace}}}density").text = str(material["density_g_cm3"])
    ET.SubElement(properties, f"{{{namespace}}}diameter").text = str(material["diameter_mm"])
    ET.SubElement(properties, f"{{{namespace}}}weight").text = str(material["nominal_net_mass_g"])
    material_settings = ET.SubElement(root, f"{{{namespace}}}settings")
    for key, cura_key in (
        ("material_print_temperature", "print temperature"),
        ("material_bed_temperature", "heated bed temperature"),
        ("cool_fan_speed", "print cooling"),
    ):
        if key in settings:
            ET.SubElement(material_settings, f"{{{namespace}}}setting", {"key": cura_key}).text = str(
                settings[key]
            )
    return cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _quality_cfg(
    *,
    name: str,
    definition: str,
    setting_version: int,
    quality_type: str,
    values: dict[str, Any],
    position: int | None,
) -> bytes:
    parser = CasePreservingConfigParser(interpolation=None)
    parser["general"] = {"version": "4", "name": name, "definition": definition}
    metadata = {
        "type": "quality_changes",
        "quality_type": quality_type,
        "intent_category": "default",
        "setting_version": str(setting_version),
    }
    if position is not None:
        metadata["position"] = str(position)
    parser["metadata"] = metadata
    parser["values"] = {
        key: "True" if value is True else "False" if value is False else str(value)
        for key, value in sorted(values.items())
    }
    output = io.StringIO()
    parser.write(output, space_around_delimiters=True)
    return output.getvalue().encode("utf-8")


def _pressure_advance_patch(machine: CuraMachine, pressure_advance: str) -> tuple[Path, bytes] | None:
    """Patch an existing machine start-G-code override; never replace inherited unknown G-code."""

    directory = machine.source_path.parent.parent / "definition_changes"
    candidates = sorted(directory.glob("*.cfg")) if directory.is_dir() else []
    machine_identity = _normalized(machine.machine_id)
    for path in candidates:
        if machine_identity not in _normalized(path.stem):
            continue
        parser = CasePreservingConfigParser(interpolation=None, strict=False)
        try:
            parser.read(path, encoding="utf-8")
        except (OSError, UnicodeError, configparser.Error):
            continue
        if not parser.has_section("values") or not parser.has_option("values", "machine_start_gcode"):
            continue
        current = parser.get("values", "machine_start_gcode")
        managed = f"{MANAGED_START}\nSET_PRESSURE_ADVANCE ADVANCE={pressure_advance}\n{MANAGED_END}"
        if MANAGED_START in current and MANAGED_END in current:
            start = current.index(MANAGED_START)
            end = current.index(MANAGED_END, start) + len(MANAGED_END)
            updated = f"{current[:start]}{managed}{current[end:]}"
        else:
            updated = f"{current.rstrip()}\n{managed}\n"
        parser.set("values", "machine_start_gcode", updated)
        output = io.StringIO()
        parser.write(output, space_around_delimiters=True)
        return path.relative_to(machine.source_path.parent.parent), output.getvalue().encode("utf-8")
    return None


def render_deployment(installation: CuraInstallation, payload: dict[str, Any]) -> RenderedDeployment:
    """Render a complete profile for one detected Cura installation."""

    printer = payload["printer"]
    profile = payload["profile"]
    material = payload["material"]
    if not isinstance(printer, dict) or not isinstance(profile, dict) or not isinstance(material, dict):
        raise ValueError("Deployment payload is missing semantic profile data.")
    machine = match_machine(installation, printer)
    definition = machine.quality_definition_id or "fdmprinter"
    quality_type = machine.quality_type or "normal"
    setting_version = installation.setting_version
    if setting_version is None:
        raise RuntimeError(f"Cura {installation.version} did not expose a setting version.")
    display_name = (
        f"Filament Manager - {material['brand']} {material['material_type']} "
        f"{material['color_name']} - {printer['nozzle_diameter_mm']} mm"
    )
    profile_slug = slug(
        f"{material['brand']}-{material['material_type']}-{material['color_name']}-{profile['id']}"
    )
    settings = profile.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("Deployment settings are invalid.")
    for key, value in settings.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key):
            raise ValueError("Deployment contains an invalid Cura setting key.")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"Cura setting {key} is not a scalar value.")
        if isinstance(value, str) and (len(value) > 500 or "\n" in value or "\r" in value):
            raise ValueError(f"Cura setting {key} contains invalid text.")
    global_values = {key: value for key, value in settings.items() if key in GLOBAL_KEYS}
    extruder_values = {key: value for key, value in settings.items() if key not in GLOBAL_KEYS}
    files = {
        Path("materials") / f"filament_manager_{profile_slug}.xml.fdm_material": _material_xml(payload),
        Path("quality_changes") / f"filament_manager_{profile_slug}_global.inst.cfg": _quality_cfg(
            name=display_name,
            definition=definition,
            setting_version=setting_version,
            quality_type=quality_type,
            values=global_values,
            position=None,
        ),
        Path("quality_changes") / f"filament_manager_{profile_slug}_extruder_0.inst.cfg": _quality_cfg(
            name=display_name,
            definition=definition,
            setting_version=setting_version,
            quality_type=quality_type,
            values=extruder_values,
            position=0,
        ),
    }
    warnings: list[str] = []
    pressure_advance = profile.get("pressure_advance")
    if pressure_advance is not None:
        if not re.fullmatch(r"\d+(?:\.\d{1,8})?", str(pressure_advance)):
            raise ValueError("Pressure advance is not a valid non-negative decimal.")
        patch = _pressure_advance_patch(machine, str(pressure_advance))
        if patch is None:
            warnings.append(
                "Pressure advance was not injected because the matched machine has no existing "
                "start-G-code override. "
                "Material and quality settings were installed without replacing inherited start G-code."
            )
        else:
            files[patch[0]] = patch[1]
    return RenderedDeployment(files=files, machine=machine, warnings=warnings)
