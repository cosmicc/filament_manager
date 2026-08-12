"""Deterministic Cura material-profile rendering."""

import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .models import CuraInstallation, CuraMachine

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

# Cura's material serializer uses human-readable standard keys for these settings. All
# other Cura and plugin settings are retained as cura:setting elements on the material.
STANDARD_MATERIAL_KEYS = {
    "build_volume_temperature": "build volume temperature",
    "cool_fan_speed": "print cooling",
    "default_material_bed_temperature": "heated bed temperature",
    "default_material_print_temperature": "print temperature",
    "material_standby_temperature": "standby temperature",
    "retraction_amount": "retraction amount",
    "retraction_speed": "retraction speed",
}


class MachineMatchError(RuntimeError):
    """Raised when a profile cannot be safely mapped to one Cura machine."""


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

    expected_names = {
        _normalized(str(printer.get("name", ""))),
        _normalized(str(printer.get("code", ""))),
    }
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
    """Render all approved profile settings into one Cura material container."""

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
    guid = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"filament-manager-{payload['source_kind']}:{payload['source_id']}",
    )
    ET.SubElement(metadata, f"{{{namespace}}}GUID").text = str(guid)
    properties = ET.SubElement(root, f"{{{namespace}}}properties")
    ET.SubElement(properties, f"{{{namespace}}}density").text = str(material["density_g_cm3"])
    ET.SubElement(properties, f"{{{namespace}}}diameter").text = str(material["diameter_mm"])
    ET.SubElement(properties, f"{{{namespace}}}weight").text = str(material["nominal_net_mass_g"])
    material_settings = ET.SubElement(root, f"{{{namespace}}}settings")
    for key, value in sorted(settings.items()):
        if key in STANDARD_MATERIAL_KEYS:
            element = ET.SubElement(
                material_settings,
                f"{{{namespace}}}setting",
                {"key": STANDARD_MATERIAL_KEYS[key]},
            )
        else:
            element = ET.SubElement(
                material_settings,
                f"{{{cura_namespace}}}setting",
                {"key": key},
            )
        element.text = "True" if value is True else "False" if value is False else str(value)
    return cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))


PLUGIN_INIT = b'''"""Register Filament Manager's material-visibility extension."""

from . import FilamentManagerVisibility

def getMetaData():
    return {}

def register(app):
    return {"extension": FilamentManagerVisibility.FilamentManagerVisibility()}
'''

PLUGIN_MODULE = b'''"""Show only Filament Manager material roots in Cura's material selectors."""

from UM.Extension import Extension
from cura.Machines.Models.BaseMaterialsModel import BaseMaterialsModel

MANAGED_PREFIX = "filament_manager_"

class FilamentManagerVisibility(Extension):
    def __init__(self):
        super().__init__()
        if getattr(BaseMaterialsModel, "_filament_manager_patched", False):
            return
        original_update = BaseMaterialsModel._update

        def managed_update(model):
            original_update(model)
            model._available_materials = {
                key: material
                for key, material in model._available_materials.items()
                if key == "empty_material" or key.startswith(MANAGED_PREFIX)
            }

        BaseMaterialsModel._update = managed_update
        BaseMaterialsModel._filament_manager_patched = True
'''

PLUGIN_METADATA = b"""{
  "name": "Filament Manager Material Visibility",
  "author": "Filament Manager",
  "version": "1.0.0",
  "description": "Shows only the authoritative Filament Manager material library.",
  "api": 5,
  "supported_sdk_versions": ["8.0.0"]
}
"""


def _visibility_plugin_files() -> dict[Path, bytes]:
    """Return the managed Cura plugin that hides non-authoritative choices."""

    plugin_root = Path("plugins") / "FilamentManagerVisibility" / "FilamentManagerVisibility"
    return {
        plugin_root / "__init__.py": PLUGIN_INIT,
        plugin_root / "FilamentManagerVisibility.py": PLUGIN_MODULE,
        plugin_root / "plugin.json": PLUGIN_METADATA,
    }


def render_deployment(installation: CuraInstallation, payload: dict[str, Any]) -> RenderedDeployment:
    """Render every desired material matching this Cura installation."""

    if payload.get("schema_version") != 2 or payload.get("hide_bundled_materials") is not True:
        raise ValueError("Deployment payload is not an authoritative Cura library.")
    materials = payload.get("materials")
    if not isinstance(materials, list) or not materials:
        raise ValueError("Deployment contains no material library entries.")
    files = _visibility_plugin_files()
    machines: list[CuraMachine] = []
    warnings: list[str] = []
    for entry in materials:
        if not isinstance(entry, dict):
            raise ValueError("Deployment contains an invalid material entry.")
        printer = entry.get("printer")
        profile = entry.get("profile")
        material = entry.get("material")
        if not isinstance(printer, dict) or not isinstance(profile, dict) or not isinstance(material, dict):
            raise ValueError("Deployment payload is missing semantic profile data.")
        try:
            machine = match_machine(installation, printer)
        except MachineMatchError as error:
            warnings.append(str(error))
            continue
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
        source_kind = str(entry.get("source_kind") or "material")
        source_id = str(entry.get("source_id") or profile.get("id") or "")
        profile_slug = slug(
            f"{source_kind}-{material['brand']}-{material['material_type']}-"
            f"{material['color_name']}-{source_id}"
        )
        files[Path("materials") / f"filament_manager_{profile_slug}.xml.fdm_material"] = _material_xml(entry)
        machines.append(machine)
    if not machines:
        raise MachineMatchError("No desired material matches a machine in this Cura installation.")
    return RenderedDeployment(files=files, machine=machines[0], warnings=warnings)
