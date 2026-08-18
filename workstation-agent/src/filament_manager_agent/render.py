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
    managed_material_setting_keys: frozenset[str]


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
    supplied_guid = payload.get("cura_material_guid")
    guid = (
        uuid.UUID(str(supplied_guid))
        if supplied_guid is not None
        else uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"filament-manager-{payload['source_kind']}:{payload['source_id']}",
        )
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


PLUGIN_INIT = b'''"""Register Filament Manager's material ownership extension."""

from . import FilamentManagerVisibility

def getMetaData():
    return {}

def register(app):
    return {"extension": FilamentManagerVisibility.FilamentManagerVisibility()}
'''

PLUGIN_MODULE_TEMPLATE = '''"""Enforce Filament Manager material ownership inside Cura."""

from PyQt6.QtCore import QTimer
from UM.Application import Application
from UM.Extension import Extension
from UM.Logger import Logger
from cura.Machines.Models.BaseMaterialsModel import BaseMaterialsModel

MANAGED_PREFIX = "filament_manager_"
MANAGED_SETTING_KEYS = frozenset(__MANAGED_SETTING_KEYS__)


def _favorite_templates(model):
    """Add every managed Template material to Cura's favorite-material set."""

    preferences = Application.getInstance().getPreferences()
    current = str(preferences.getValue("cura/favorite_materials") or "")
    favorites = {value for value in current.split(";") if value}
    for material_id, material in model._available_materials.items():
        if material_id == "empty_material" or not material_id.startswith(MANAGED_PREFIX):
            continue
        try:
            if str(material.getMetaDataEntry("brand", "")) == "Template":
                favorites.add(material_id)
        except Exception:
            Logger.log("w", "Unable to inspect managed template favorite metadata")
    updated = ";".join(sorted(favorites))
    if updated != current:
        preferences.setValue("cura/favorite_materials", updated)

class FilamentManagerVisibility(Extension):
    def __init__(self):
        super().__init__()
        self._enforcing = False
        self._scheduled = False
        self._connected_containers = set()
        application = Application.getInstance()
        machine_manager = application.getMachineManager()
        for signal_name in (
            "activeMaterialChanged",
            "activeQualityChanged",
            "activeQualityChangesGroupChanged",
            "activeStackChanged",
            "globalContainerChanged",
        ):
            signal = getattr(machine_manager, signal_name, None)
            if signal is not None:
                signal.connect(self._schedule_enforcement)
        if getattr(BaseMaterialsModel, "_filament_manager_patched", False):
            self._schedule_enforcement()
            return
        original_update = BaseMaterialsModel._update

        def managed_update(model):
            original_update(model)
            model._available_materials = {
                key: material
                for key, material in model._available_materials.items()
                if key == "empty_material" or key.startswith(MANAGED_PREFIX)
            }
            _favorite_templates(model)

        BaseMaterialsModel._update = managed_update
        BaseMaterialsModel._filament_manager_patched = True
        self._schedule_enforcement()

    def _schedule_enforcement(self, *args):
        if self._scheduled:
            return
        self._scheduled = True
        QTimer.singleShot(0, self._enforce_material_settings)

    @staticmethod
    def _is_managed_material(stack):
        material = getattr(stack, "material", None)
        if material is None:
            return False
        material_id = str(material.getMetaDataEntry("base_file", material.getId()) or "")
        return material_id.startswith(MANAGED_PREFIX)

    def _watch(self, container):
        identity = id(container)
        if identity in self._connected_containers:
            return
        container.propertyChanged.connect(self._schedule_enforcement)
        self._connected_containers.add(identity)

    def _enforce_material_settings(self):
        self._scheduled = False
        if self._enforcing:
            return
        self._enforcing = True
        try:
            global_stack = Application.getInstance().getGlobalContainerStack()
            if global_stack is None:
                return
            extruders = list(global_stack.extruderList)
            stacks = [global_stack] + extruders
            for stack in stacks:
                quality_changes = stack.qualityChanges
                self._watch(stack.userChanges)
                self._watch(quality_changes)
                changed = False
                for key in MANAGED_SETTING_KEYS.intersection(quality_changes.getAllKeys()):
                    quality_changes.removeInstance(key, postpone_emit=True)
                    changed = True
                if changed:
                    quality_changes.sendPostponedEmits()

            # Remove stale top-layer values from the global stack and any
            # extruder that is no longer using a managed material.
            for stack in stacks:
                if stack is not global_stack and self._is_managed_material(stack):
                    continue
                user_changes = stack.userChanges
                changed = False
                for key in MANAGED_SETTING_KEYS.intersection(user_changes.getAllKeys()):
                    user_changes.removeInstance(key, postpone_emit=True)
                    changed = True
                if changed:
                    user_changes.sendPostponedEmits()

            # Cura's built-in and custom quality layers sit above its material
            # layer. Mirror only values explicitly supplied by the selected
            # managed material into the supported top user layer so the material
            # remains authoritative without modifying bundled quality profiles.
            for stack in extruders:
                if not self._is_managed_material(stack):
                    continue
                material = stack.material
                user_changes = stack.userChanges
                material_keys = MANAGED_SETTING_KEYS.intersection(material.getAllKeys())
                stale_keys = MANAGED_SETTING_KEYS.intersection(user_changes.getAllKeys()) - material_keys
                for key in stale_keys:
                    user_changes.removeInstance(key, postpone_emit=True)
                if stale_keys:
                    user_changes.sendPostponedEmits()
                for key in material_keys:
                    material_value = material.getProperty(key, "value")
                    current_value = user_changes.getProperty(key, "value")
                    if str(current_value) != str(material_value):
                        user_changes.setProperty(key, "value", material_value)
            Logger.log("d", "Filament Manager material settings enforced")
        except Exception:
            Logger.logException("e", "Filament Manager could not enforce material settings")
        finally:
            self._enforcing = False
'''

PLUGIN_METADATA = b"""{
  "name": "Filament Manager Material Visibility",
  "author": "Filament Manager",
  "version": "2.0.0",
  "description": "Shows, favorites, and enforces the authoritative Filament Manager material library.",
  "api": 5,
  "supported_sdk_versions": ["8.0.0"]
}
"""


def _visibility_plugin_files(managed_setting_keys: frozenset[str]) -> dict[Path, bytes]:
    """Return the managed Cura plugin with its bounded central setting catalog."""

    plugin_root = Path("plugins") / "FilamentManagerVisibility" / "FilamentManagerVisibility"
    module = PLUGIN_MODULE_TEMPLATE.replace(
        "__MANAGED_SETTING_KEYS__",
        repr(tuple(sorted(managed_setting_keys))),
    ).encode("utf-8")
    return {
        plugin_root / "__init__.py": PLUGIN_INIT,
        plugin_root / "FilamentManagerVisibility.py": module,
        plugin_root / "plugin.json": PLUGIN_METADATA,
    }


def render_deployment(installation: CuraInstallation, payload: dict[str, Any]) -> RenderedDeployment:
    """Render every desired material matching this Cura installation."""

    if payload.get("schema_version") != 3 or payload.get("hide_bundled_materials") is not True:
        raise ValueError("Deployment payload is not an authoritative Cura library.")
    raw_managed_keys = payload.get("managed_material_setting_keys")
    if not isinstance(raw_managed_keys, list) or not raw_managed_keys:
        raise ValueError("Deployment is missing its managed Cura setting catalog.")
    if any(
        not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key) for key in raw_managed_keys
    ):
        raise ValueError("Deployment contains an invalid managed Cura setting key.")
    managed_setting_keys = frozenset(raw_managed_keys)
    if len(managed_setting_keys) != len(raw_managed_keys):
        raise ValueError("Deployment contains duplicate managed Cura setting keys.")
    materials = payload.get("materials")
    if not isinstance(materials, list) or not materials:
        raise ValueError("Deployment contains no material library entries.")
    files = _visibility_plugin_files(managed_setting_keys)
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
    return RenderedDeployment(
        files=files,
        machine=machines[0],
        warnings=warnings,
        managed_material_setting_keys=managed_setting_keys,
    )
