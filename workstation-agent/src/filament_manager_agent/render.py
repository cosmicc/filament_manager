"""Deterministic Cura material-profile rendering."""

import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from .models import CuraInstallation, CuraMachine

SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

# Cura's material serializer uses human-readable standard keys for these settings. All
# other Cura and plugin settings are retained as cura:setting elements on the material.
STANDARD_MATERIAL_KEYS = {
    "build_volume_temperature": "build volume temperature",
    "cool_fan_speed": "print cooling",
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
    cleanup_material_setting_keys: frozenset[str]
    material_id_migrations: dict[str, str]


def slug(value: str, *, maximum: int = 72) -> str:
    """Create a bounded portable filename fragment."""

    result = SLUG_PATTERN.sub("_", value.casefold()).strip("_")
    return (result or "profile")[:maximum]


def _normalized(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _description_value(value: object) -> str:
    """Return one safe display line for optional filament identity metadata."""

    if value is None:
        return "None"
    if not isinstance(value, str):
        raise ValueError("Filament description metadata must be text or null.")
    normalized = value.strip()
    if not normalized:
        return "None"
    if len(normalized) > 96 or "\n" in normalized or "\r" in normalized:
        raise ValueError("Filament description metadata contains invalid text.")
    return normalized


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
    ET.SubElement(metadata, f"{{{namespace}}}description").text = (
        f"Filament Filler: {_description_value(material.get('filler'))}\n"
        f"Filament Finish: {_description_value(material.get('finish'))}"
    )
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
    return {"extension": FilamentManagerVisibility.FilamentManagerVisibility(app)}
'''

PLUGIN_MODULE_TEMPLATE = '''"""Enforce Filament Manager material ownership inside Cura."""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QTimer
from UM.Extension import Extension
from UM.Logger import Logger
from cura.Machines.Models.BaseMaterialsModel import BaseMaterialsModel

MANAGED_PREFIX = "filament_manager_"
MANAGED_SETTING_KEYS = frozenset(__MANAGED_SETTING_KEYS__)
EDITABLE_SETTING_KEYS = frozenset(__EDITABLE_SETTING_KEYS__)
TEMPLATE_ONLY_SETTING_KEYS = frozenset(__TEMPLATE_ONLY_SETTING_KEYS__)
RETIRED_SETTING_KEYS = frozenset(__RETIRED_SETTING_KEYS__)
MANAGED_MATERIAL_COSTS = __MANAGED_MATERIAL_COSTS__
KLIPPER_SETTING_KEYS = frozenset({
    "klipper_pressure_advance_factor",
    "klipper_smooth_time_enable",
    "klipper_smooth_time_factor",
})
MATERIAL_SETTINGS_STATUS_SCHEMA_VERSION = 1
MATERIAL_SETTINGS_STATUS_PATH = Path(__file__).with_name("material-settings-status.json")
MANAGED_MATERIAL_EDITS_SCHEMA_VERSION = 1
MANAGED_MATERIAL_EDITS_PATH = Path(__file__).with_name("managed-material-edits.json")
MANAGED_MACHINE_START_GCODE = (
    "FILAMENT_MANAGER_START_PRINT "
    "MATERIAL_GUID={material_guid} "
    "BED_TEMP={material_bed_temperature_layer_0} "
    "EXTRUDER_TEMP={material_print_temperature_layer_0} "
    "CHAMBER_TEMP={build_volume_temperature}"
)
MANAGED_MACHINE_END_GCODE = "END_PRINT"
GUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
MISSING_VALUE = object()
_PENDING_MATERIAL_EDITS_CACHE = {}
_PENDING_MATERIAL_EDITS_SIGNATURE = None


def _catalog_checksum():
    """Return one deterministic checksum for the deployed visible-setting contract."""

    serialized = "\\n".join(sorted(MANAGED_SETTING_KEYS)).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _available_material_setting_keys(application):
    """Return deployed keys Cura can resolve for the active machine definition."""

    global_stack = application.getGlobalContainerStack()
    if global_stack is None:
        return None
    stacks = [global_stack] + list(global_stack.extruderList)
    available = set()
    for key in MANAGED_SETTING_KEYS:
        for stack in stacks:
            try:
                if key not in stack.getAllKeys():
                    continue
                available.add(key)
                break
            except Exception:
                continue
    return available


def _material_settings_status_payload(application):
    """Build a value-free receipt for the settings Cura actually exposes."""

    preferences = application.getPreferences()
    visible_raw = str(preferences.getValue("material_settings/visible_settings") or "")
    visible = {key for key in visible_raw.split(";") if key}
    available = _available_material_setting_keys(application)
    if available is None:
        exposed = set()
        missing = set(MANAGED_SETTING_KEYS)
        status = "waiting_for_machine"
    else:
        exposed = MANAGED_SETTING_KEYS & visible & available
        missing = MANAGED_SETTING_KEYS - exposed
        status = "healthy" if not missing and not (visible & RETIRED_SETTING_KEYS) else "degraded"
    return {
        "schema_version": MATERIAL_SETTINGS_STATUS_SCHEMA_VERSION,
        "catalog_checksum": _catalog_checksum(),
        "status": status,
        "expected_count": len(MANAGED_SETTING_KEYS),
        "exposed_count": len(exposed),
        "missing_keys": sorted(missing),
        "unexpected_keys": sorted(visible & RETIRED_SETTING_KEYS),
        "material_settings_plugin_ready": (
            MANAGED_SETTING_KEYS <= visible and not (visible & RETIRED_SETTING_KEYS)
        ),
        "klipper_settings_plugin_ready": (
            False if available is None else KLIPPER_SETTING_KEYS <= available
        ),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_material_settings_status(application):
    """Atomically persist the sanitized receipt for the outbound workstation agent."""

    payload = _material_settings_status_payload(application)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".material-settings-status-",
        dir=MATERIAL_SETTINGS_STATUS_PATH.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, MATERIAL_SETTINGS_STATUS_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


def _favorite_templates(application, model):
    """Add every managed Template material to Cura's favorite-material set."""

    preferences = application.getPreferences()
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


def _configure_material_settings_plugin(application):
    """Add the central catalog without replacing the operator's other selections."""

    preferences = application.getPreferences()
    current = str(preferences.getValue("material_settings/visible_settings") or "")
    selected = {key for key in current.split(";") if key}
    updated = (selected | MANAGED_SETTING_KEYS) - RETIRED_SETTING_KEYS
    rendered = ";".join(sorted(updated))
    if rendered != current:
        preferences.setValue("material_settings/visible_settings", rendered)


def _material_guid(stack):
    """Return the canonical GUID for a selected managed material, if available."""

    material = getattr(stack, "material", None)
    if material is None:
        return None
    for candidate in (
        material.getMetaDataEntry("GUID", ""),
        material.getMetaDataEntry("guid", ""),
        material.getId(),
    ):
        value = str(candidate or "").strip()
        if GUID_PATTERN.fullmatch(value):
            return value.lower()
    return None


def _load_pending_material_edits():
    """Load the bounded local edit receipt without exposing values in logs."""

    global _PENDING_MATERIAL_EDITS_CACHE, _PENDING_MATERIAL_EDITS_SIGNATURE
    try:
        if MANAGED_MATERIAL_EDITS_PATH.is_symlink():
            return {}
        if not MANAGED_MATERIAL_EDITS_PATH.exists():
            _PENDING_MATERIAL_EDITS_CACHE = {}
            _PENDING_MATERIAL_EDITS_SIGNATURE = None
            return {}
        stat = MANAGED_MATERIAL_EDITS_PATH.stat()
        if stat.st_size > 128 * 1024:
            return {}
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature == _PENDING_MATERIAL_EDITS_SIGNATURE:
            return _PENDING_MATERIAL_EDITS_CACHE
        payload = json.loads(MANAGED_MATERIAL_EDITS_PATH.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return {}
    materials = payload.get("materials")
    _PENDING_MATERIAL_EDITS_CACHE = materials if isinstance(materials, dict) else {}
    _PENDING_MATERIAL_EDITS_SIGNATURE = signature
    return _PENDING_MATERIAL_EDITS_CACHE


def _write_pending_material_edits(materials):
    """Atomically persist bounded managed edits for the outbound agent."""

    payload = {
        "schema_version": MANAGED_MATERIAL_EDITS_SCHEMA_VERSION,
        "materials": materials,
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".managed-material-edits-",
        dir=MANAGED_MATERIAL_EDITS_PATH.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, MANAGED_MATERIAL_EDITS_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


def _record_pending_material_edit(stack, key, value):
    """Queue one editable managed value for secure server-side validation."""

    material_guid = _material_guid(stack)
    if material_guid is None or key not in EDITABLE_SETTING_KEYS:
        return
    material = getattr(stack, "material", None)
    is_template = (
        material is not None
        and str(material.getMetaDataEntry("brand", "")).strip() == "Template"
    )
    if key in TEMPLATE_ONLY_SETTING_KEYS and not is_template:
        return
    if not isinstance(value, (str, int, float, bool)):
        return
    rendered_value = value if isinstance(value, bool) else str(value)
    if isinstance(rendered_value, str) and (
        len(rendered_value) > 500 or "\\n" in rendered_value or "\\r" in rendered_value
    ):
        return
    materials = _load_pending_material_edits()
    material_edits = materials.get(material_guid)
    if not isinstance(material_edits, dict):
        material_edits = {}
        materials[material_guid] = material_edits
    material_edits[key] = rendered_value
    if len(materials) <= 100 and len(material_edits) <= len(EDITABLE_SETTING_KEYS):
        _write_pending_material_edits(materials)


def _is_managed_material(stack):
    """Return whether one Cura stack selected a Filament Manager material."""

    material = getattr(stack, "material", None)
    if material is None:
        return False
    material_id = str(material.getMetaDataEntry("base_file", material.getId()) or "")
    return material_id.startswith(MANAGED_PREFIX)


def _managed_material_value(stack, key):
    """Resolve an explicit canonical material value without dirtying the quality profile."""

    if key not in MANAGED_SETTING_KEYS or not _is_managed_material(stack):
        return MISSING_VALUE
    material = stack.material
    material_guid = _material_guid(stack)
    pending = _load_pending_material_edits().get(material_guid, {})
    if isinstance(pending, dict) and key in pending:
        return pending[key]
    if key not in material.getAllKeys():
        return MISSING_VALUE
    return material.getProperty(key, "value")


def _managed_machine_gcode(stack, key):
    """Return the app-owned print boundary for a managed material only."""

    if not _is_managed_material(stack):
        return MISSING_VALUE
    if key == "machine_start_gcode":
        return MANAGED_MACHINE_START_GCODE
    if key == "machine_end_gcode":
        return MANAGED_MACHINE_END_GCODE
    return MISSING_VALUE


def _install_runtime_material_overlay():
    """Make managed values authoritative without placing them in Cura user changes."""

    from cura.Settings.CuraContainerStack import CuraContainerStack

    if getattr(CuraContainerStack, "_filament_manager_overlay_patched", False):
        return
    original_get_property = CuraContainerStack.getProperty

    def managed_get_property(stack, key, property_name, *args, **kwargs):
        if property_name == "value":
            machine_gcode = _managed_machine_gcode(stack, key)
            if machine_gcode is not MISSING_VALUE:
                return machine_gcode
            value = _managed_material_value(stack, key)
            if value is not MISSING_VALUE:
                return value
        return original_get_property(stack, key, property_name, *args, **kwargs)

    CuraContainerStack.getProperty = managed_get_property
    CuraContainerStack._filament_manager_overlay_patched = True


def _configure_material_costs(application):
    """Merge managed product costs into Cura without changing other materials."""

    preferences = application.getPreferences()
    add_preference = getattr(preferences, "addPreference", None)
    if add_preference is not None:
        add_preference("filament_manager/material_cost_guids", "[]")
    current_raw = str(preferences.getValue("cura/material_settings") or "{}")
    previous_raw = str(
        preferences.getValue("filament_manager/material_cost_guids") or "[]"
    )
    try:
        current = json.loads(current_raw)
    except (TypeError, ValueError):
        current = {}
    if not isinstance(current, dict):
        current = {}
    try:
        previous = json.loads(previous_raw)
    except (TypeError, ValueError):
        previous = []
    if not isinstance(previous, list):
        previous = []
    for guid in previous:
        if isinstance(guid, str):
            current.pop(guid, None)
    current.update(MANAGED_MATERIAL_COSTS)
    updated = json.dumps(current, sort_keys=True, separators=(",", ":"))
    if updated != current_raw:
        preferences.setValue("cura/material_settings", updated)
    managed_guids = json.dumps(sorted(MANAGED_MATERIAL_COSTS), separators=(",", ":"))
    if managed_guids != previous_raw:
        preferences.setValue("filament_manager/material_cost_guids", managed_guids)

class FilamentManagerVisibility(Extension):
    def __init__(self, application):
        super().__init__()
        self._application = application
        self._initialized = False
        self._enforcing = False
        self._scheduled = False
        self._connected_containers = set()
        self._install_material_filter()
        application.initializationFinished.connect(self._initialize)
        if getattr(application, "started", False):
            QTimer.singleShot(0, self._initialize)

    def _initialize(self):
        """Connect to machine state only after Cura has completed initialization."""

        if self._initialized:
            return
        try:
            _configure_material_settings_plugin(self._application)
            _configure_material_costs(self._application)
            _install_runtime_material_overlay()
            preference_signal = getattr(
                self._application.getPreferences(), "preferenceChanged", None
            )
            if preference_signal is not None:
                preference_signal.connect(self._on_preference_changed)
            machine_manager = self._application.getMachineManager()
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
        except Exception:
            Logger.logException("e", "Filament Manager could not initialize material enforcement")
            return
        self._initialized = True
        self._schedule_enforcement()

    def _on_preference_changed(self, name):
        """Repair manual drift in the Material Settings plugin selection."""

        if name != "material_settings/visible_settings" or self._enforcing:
            return
        _configure_material_settings_plugin(self._application)
        self._schedule_enforcement()

    def _install_material_filter(self):
        """Patch future selector updates without constructing Cura managers early."""

        if getattr(BaseMaterialsModel, "_filament_manager_patched", False):
            return
        original_update = BaseMaterialsModel._update
        extension = self

        def managed_update(model):
            original_update(model)
            if not extension._initialized:
                return
            model._available_materials = {
                key: material
                for key, material in model._available_materials.items()
                if key == "empty_material" or key.startswith(MANAGED_PREFIX)
            }
            _favorite_templates(extension._application, model)

        BaseMaterialsModel._update = managed_update
        BaseMaterialsModel._filament_manager_patched = True

    def _schedule_enforcement(self, *args):
        if self._scheduled:
            return
        self._scheduled = True
        QTimer.singleShot(0, self._enforce_material_settings)

    def _watch(self, container, stack, *, capture_edits=False):
        identity = id(container)
        if identity in self._connected_containers:
            return

        def changed(key=None, property_name=None):
            if self._enforcing:
                return
            if capture_edits and key in EDITABLE_SETTING_KEYS and property_name in {None, "value"}:
                try:
                    _record_pending_material_edit(
                        stack,
                        key,
                        container.getProperty(key, "value"),
                    )
                except Exception:
                    Logger.log("w", "Filament Manager could not queue a managed material edit")
            self._schedule_enforcement()

        container.propertyChanged.connect(changed)
        self._connected_containers.add(identity)

    def _enforce_material_settings(self):
        self._scheduled = False
        if self._enforcing:
            return
        self._enforcing = True
        try:
            global_stack = self._application.getGlobalContainerStack()
            if global_stack is None:
                _write_material_settings_status(self._application)
                return
            extruders = list(global_stack.extruderList)
            stacks = [global_stack] + extruders
            for stack in stacks:
                quality_changes = stack.qualityChanges
                self._watch(stack.userChanges, stack, capture_edits=True)
                self._watch(quality_changes, stack)
                if _is_managed_material(stack):
                    self._watch(stack.material, stack, capture_edits=True)
                changed = False
                for key in MANAGED_SETTING_KEYS.intersection(quality_changes.getAllKeys()):
                    quality_changes.removeInstance(key, postpone_emit=True)
                    changed = True
                if changed:
                    quality_changes.sendPostponedEmits()

            # Managed values are resolved by the runtime material overlay. Keep
            # Cura's top user layer reserved for genuine quality-profile edits
            # so Save Profile never includes application-owned material values.
            for stack in stacks:
                user_changes = stack.userChanges
                changed = False
                for key in MANAGED_SETTING_KEYS.intersection(user_changes.getAllKeys()):
                    user_changes.removeInstance(key, postpone_emit=True)
                    changed = True
                if changed:
                    user_changes.sendPostponedEmits()

            Logger.log("d", "Filament Manager material settings enforced")
            _write_material_settings_status(self._application)
        except Exception:
            Logger.logException("e", "Filament Manager could not enforce material settings")
        finally:
            self._enforcing = False
'''

PLUGIN_METADATA = b"""{
  "name": "Filament Manager Material Visibility",
  "author": "Filament Manager",
  "version": "2.2.0",
  "description": "Enforces the Filament Manager material library and print boundary.",
  "api": 5,
  "supported_sdk_versions": ["8.0.0"]
}
"""


def _visibility_plugin_files(
    managed_setting_keys: frozenset[str],
    editable_setting_keys: frozenset[str],
    template_only_setting_keys: frozenset[str],
    retired_setting_keys: frozenset[str],
    managed_material_costs: dict[str, dict[str, float]],
) -> dict[Path, bytes]:
    """Return the managed Cura plugin with its bounded central setting catalog."""

    plugin_root = Path("plugins") / "FilamentManagerVisibility" / "FilamentManagerVisibility"
    module = (
        PLUGIN_MODULE_TEMPLATE.replace(
            "__MANAGED_SETTING_KEYS__",
            repr(tuple(sorted(managed_setting_keys))),
        )
        .replace(
            "__EDITABLE_SETTING_KEYS__",
            repr(tuple(sorted(editable_setting_keys))),
        )
        .replace(
            "__TEMPLATE_ONLY_SETTING_KEYS__",
            repr(tuple(sorted(template_only_setting_keys))),
        )
        .replace(
            "__RETIRED_SETTING_KEYS__",
            repr(tuple(sorted(retired_setting_keys))),
        )
        .replace(
            "__MANAGED_MATERIAL_COSTS__",
            repr(managed_material_costs),
        )
        .encode("utf-8")
    )
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
    raw_editable_keys = payload.get("editable_material_setting_keys")
    if not isinstance(raw_editable_keys, list) or not raw_editable_keys:
        raise ValueError("Deployment is missing its editable Cura setting catalog.")
    if any(
        not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key)
        for key in raw_editable_keys
    ):
        raise ValueError("Deployment contains an invalid editable Cura setting key.")
    editable_setting_keys = frozenset(raw_editable_keys)
    if len(editable_setting_keys) != len(raw_editable_keys):
        raise ValueError("Deployment contains duplicate editable Cura setting keys.")
    if not editable_setting_keys <= managed_setting_keys:
        raise ValueError("Editable Cura settings must be part of the managed catalog.")
    raw_template_only_keys = payload.get("template_only_material_setting_keys")
    if not isinstance(raw_template_only_keys, list):
        raise ValueError("Deployment is missing its template-only Cura setting catalog.")
    if any(
        not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key)
        for key in raw_template_only_keys
    ):
        raise ValueError("Deployment contains an invalid template-only Cura setting key.")
    template_only_setting_keys = frozenset(raw_template_only_keys)
    if len(template_only_setting_keys) != len(raw_template_only_keys):
        raise ValueError("Deployment contains duplicate template-only Cura setting keys.")
    if not template_only_setting_keys <= managed_setting_keys:
        raise ValueError("Template-only Cura settings must be part of the managed catalog.")
    raw_retired_keys = payload.get("retired_material_setting_keys", [])
    if not isinstance(raw_retired_keys, list) or any(
        not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key) for key in raw_retired_keys
    ):
        raise ValueError("Deployment contains an invalid retired Cura setting catalog.")
    retired_setting_keys = frozenset(raw_retired_keys)
    if len(retired_setting_keys) != len(raw_retired_keys):
        raise ValueError("Deployment contains duplicate retired Cura setting keys.")
    materials = payload.get("materials")
    if not isinstance(materials, list) or not materials:
        raise ValueError("Deployment contains no material library entries.")
    files: dict[Path, bytes] = {}
    machines: list[CuraMachine] = []
    warnings: list[str] = []
    managed_material_costs: dict[str, dict[str, float]] = {}
    material_id_migrations: dict[str, str] = {}
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
        supplied_guid = entry.get("cura_material_guid")
        material_guid = str(
            uuid.UUID(str(supplied_guid))
            if supplied_guid is not None
            else uuid.uuid5(uuid.NAMESPACE_URL, f"filament-manager-{source_kind}:{source_id}")
        )
        raw_cost_basis = material.get("cura_cost_basis")
        if raw_cost_basis is not None:
            if not isinstance(raw_cost_basis, dict):
                raise ValueError("Deployment contains an invalid Cura cost basis.")
            try:
                spool_weight = Decimal(str(raw_cost_basis["spool_weight_g"]))
                spool_cost = Decimal(str(raw_cost_basis["spool_cost"]))
            except (InvalidOperation, KeyError, TypeError, ValueError) as error:
                raise ValueError("Deployment contains an invalid Cura cost basis.") from error
            if not spool_weight.is_finite() or not spool_cost.is_finite():
                raise ValueError("Deployment contains a non-finite Cura cost basis.")
            if spool_weight <= 0 or spool_cost < 0:
                raise ValueError("Deployment contains an out-of-range Cura cost basis.")
            managed_material_costs[material_guid] = {
                "spool_weight": float(spool_weight),
                "spool_cost": float(spool_cost),
            }
        # Cura uses the filename stem as the container ID referenced by its
        # extruder stack. Keep it independent of mutable brand/color metadata.
        profile_slug = slug(f"{source_kind}-{source_id}")
        container_id = f"filament_manager_{profile_slug}"
        files[Path("materials") / f"{container_id}.xml.fdm_material"] = _material_xml(entry)
        raw_legacy_source_ids = entry.get("legacy_source_ids", [])
        if not isinstance(raw_legacy_source_ids, list) or len(raw_legacy_source_ids) > 10_000:
            raise ValueError("Deployment contains an invalid legacy material identity list.")
        for legacy_source_id in raw_legacy_source_ids:
            try:
                validated_legacy_id = str(uuid.UUID(str(legacy_source_id)))
            except (TypeError, ValueError) as error:
                raise ValueError("Deployment contains an invalid legacy material identity.") from error
            legacy_slug = slug(
                f"{source_kind}-{material['brand']}-{material['material_type']}-"
                f"{material['color_name']}-{validated_legacy_id}"
            )
            legacy_container_id = f"filament_manager_{legacy_slug}"
            if legacy_container_id != container_id:
                material_id_migrations[legacy_container_id] = container_id
            revision_only_container_id = f"filament_manager_{slug(f'{source_kind}-{validated_legacy_id}')}"
            if revision_only_container_id != container_id:
                material_id_migrations[revision_only_container_id] = container_id
        metadata_scoped_container_id = "filament_manager_" + slug(
            f"{source_kind}-{material['brand']}-{material['material_type']}-"
            f"{material['color_name']}-{source_id}"
        )
        if metadata_scoped_container_id != container_id:
            material_id_migrations[metadata_scoped_container_id] = container_id
        machines.append(machine)
    if not machines:
        raise MachineMatchError("No desired material matches a machine in this Cura installation.")
    files.update(
        _visibility_plugin_files(
            managed_setting_keys,
            editable_setting_keys,
            template_only_setting_keys,
            retired_setting_keys,
            managed_material_costs,
        )
    )
    return RenderedDeployment(
        files=files,
        machine=machines[0],
        warnings=warnings,
        managed_material_setting_keys=managed_setting_keys,
        cleanup_material_setting_keys=managed_setting_keys | retired_setting_keys,
        material_id_migrations=material_id_migrations,
    )
