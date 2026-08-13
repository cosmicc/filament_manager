"""Cura process, user-data, version, and machine-instance discovery."""

import configparser
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from xml.etree.ElementTree import Element

import psutil
from defusedxml import ElementTree as ET

from .models import CuraInstallation, CuraMachine, CuraMaterial

VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+){1,3}$")
SETTING_VERSION_PATTERN = re.compile(r"^\s*setting_version\s*=\s*(\d+)\s*$", re.MULTILINE)
MATERIAL_SETTING_KEYS = frozenset(
    {
        "build_volume_temperature",
        "cool_fan_enabled",
        "cool_fan_full_layer",
        "cool_fan_speed",
        "cool_fan_speed_0",
        "cool_fan_speed_max",
        "cool_fan_speed_min",
        "cool_min_layer_time",
        "cool_min_layer_time_fan_speed_max",
        "cool_min_speed",
        "default_material_bed_temperature",
        "default_material_print_temperature",
        "hole_xy_offset",
        "hole_xy_offset_max_diameter",
        "infill_material_flow",
        "klipper_pressure_advance_factor",
        "klipper_smooth_time_enable",
        "klipper_smooth_time_factor",
        "limit_support_retractions",
        "material_bed_temperature",
        "material_bed_temperature_layer_0",
        "material_final_print_temperature",
        "material_flow",
        "material_flow_layer_0",
        "material_initial_print_temperature",
        "material_print_temperature",
        "material_print_temperature_layer_0",
        "material_standby_temperature",
        "retract_at_layer_change",
        "retraction_amount",
        "retraction_enable",
        "retraction_min_travel",
        "retraction_prime_speed",
        "retraction_retract_speed",
        "retraction_speed",
        "roofing_material_flow",
        "skirt_brim_material_flow",
        "skirt_brim_speed",
        "speed_infill",
        "speed_layer_0",
        "speed_print",
        "speed_print_layer_0",
        "speed_roofing",
        "speed_support",
        "speed_topbottom",
        "speed_travel",
        "speed_travel_layer_0",
        "speed_wall",
        "speed_wall_0",
        "speed_wall_x",
        "support_angle",
        "support_material_flow",
        "xy_offset",
        "xy_offset_layer_0",
    }
)
STANDARD_MATERIAL_KEYS = {
    "build volume temperature": "build_volume_temperature",
    "heated bed temperature": "default_material_bed_temperature",
    "print cooling": "cool_fan_speed",
    "print temperature": "default_material_print_temperature",
    "retraction amount": "retraction_amount",
    "retraction speed": "retraction_speed",
    "standby temperature": "material_standby_temperature",
}


def platform_key() -> str:
    """Return the server platform identifier supported by this distribution."""

    if sys.platform == "win32":
        return "windows_11"
    if sys.platform.startswith("linux"):
        return "arch_linux"
    raise RuntimeError("The workstation agent supports Arch Linux and Windows 11 only.")


def cura_is_running() -> bool:
    """Detect Cura conservatively before modifying its user data."""

    for process in psutil.process_iter(["name", "exe", "cmdline"]):
        try:
            details = process.info
            candidates = [str(details.get("name") or ""), str(details.get("exe") or "")]
            candidates.extend(str(item) for item in (details.get("cmdline") or []))
            if any("cura" in Path(value).name.casefold() for value in candidates if value):
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue
    return False


def _candidate_roots() -> list[tuple[str, Path]]:
    override = os.environ.get("FILAMENT_MANAGER_CURA_ROOTS")
    if override:
        return [
            ("Configured Cura", Path(value).expanduser()) for value in override.split(os.pathsep) if value
        ]
    home = Path.home()
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return [("Windows Cura", appdata / "cura")]
    return [
        ("Linux Cura", home / ".local" / "share" / "cura"),
        ("Flatpak Cura", home / ".var" / "app" / "com.ultimaker.cura" / "data" / "cura"),
        ("Snap Cura", home / "snap" / "cura-slicer" / "current" / ".local" / "share" / "cura"),
        ("Snap Cura", home / "snap" / "cura" / "current" / ".local" / "share" / "cura"),
    ]


def _read_cfg(path: Path) -> configparser.ConfigParser | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, UnicodeError, configparser.Error):
        return None
    return parser


def _machine_from_file(path: Path) -> CuraMachine | None:
    parser = _read_cfg(path)
    if parser is None:
        return None
    general = parser["general"] if parser.has_section("general") else {}
    metadata = parser["metadata"] if parser.has_section("metadata") else {}
    machine_type = str(metadata.get("type", ""))
    if machine_type and machine_type not in {"machine", "machine_instance"}:
        return None
    display_name = str(general.get("name") or metadata.get("name") or path.stem).strip()
    containers = parser["containers"] if parser.has_section("containers") else {}
    base_containers = [
        (int(key), str(value).strip())
        for key, value in containers.items()
        if key.isdigit() and str(value).strip()
    ]
    inferred_definition = max(base_containers, default=(0, ""))[1]
    return CuraMachine(
        machine_id=path.stem.removesuffix(".global"),
        display_name=display_name,
        definition_id=(
            str(general.get("definition") or metadata.get("definition") or inferred_definition).strip()
            or None
        ),
        quality_type=str(containers.get("3") or "").strip() or None,
        variant=str(metadata.get("variant") or "").strip() or None,
        nozzle_diameter_mm=str(metadata.get("nozzle_diameter") or "").strip() or None,
        source_path=path,
    )


def _quality_definition(data_path: Path, machine: CuraMachine) -> str:
    """Infer Cura's quality-definition family from an existing machine profile."""

    identities = {
        _normalized
        for value in (machine.definition_id, machine.machine_id)
        if (_normalized := re.sub(r"[^a-z0-9]", "", (value or "").casefold()))
    }
    fallback: str | None = None
    for path in sorted((data_path / "quality_changes").glob("*.cfg"))[:200]:
        parser = _read_cfg(path)
        if parser is None or not parser.has_section("metadata") or not parser.has_section("general"):
            continue
        metadata = parser["metadata"]
        if metadata.get("type") != "quality_changes" or metadata.get("position") is not None:
            continue
        definition = str(parser["general"].get("definition") or "").strip()
        if not definition:
            continue
        fallback = fallback or definition
        stem = re.sub(r"[^a-z0-9]", "", path.stem.casefold())
        if any(identity in stem for identity in identities):
            return definition
    return fallback or "fdmprinter"


def _unique_nozzle_size(data_path: Path) -> str | None:
    """Return the nozzle size when one unambiguous local override exists."""

    values: set[str] = set()
    for path in sorted((data_path / "definition_changes").glob("*.cfg"))[:200]:
        parser = _read_cfg(path)
        if parser is not None and parser.has_section("values"):
            value = str(parser["values"].get("machine_nozzle_size") or "").strip()
            if value:
                values.add(value)
    return next(iter(values)) if len(values) == 1 else None


def _setting_version(data_path: Path) -> int | None:
    for directory in ("machine_instances", "quality_changes", "quality"):
        for path in sorted((data_path / directory).glob("*.cfg"))[:100]:
            try:
                match = SETTING_VERSION_PATTERN.search(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if match:
                return int(match.group(1))
    return None


def discover_installations() -> list[CuraInstallation]:
    """Discover writable versioned Cura user-data directories without creating them."""

    installations: list[CuraInstallation] = []
    seen: set[Path] = set()
    for channel, root in _candidate_roots():
        if not root.is_dir():
            continue
        candidates = [root] if VERSION_PATTERN.match(root.name) else list(root.iterdir())
        for candidate in sorted(candidates):
            if not candidate.is_dir() or not VERSION_PATTERN.match(candidate.name):
                continue
            resolved = candidate.resolve()
            if resolved in seen or not os.access(resolved, os.W_OK):
                continue
            seen.add(resolved)
            raw_machines = [
                machine
                for path in sorted((resolved / "machine_instances").glob("*.cfg"))[:100]
                if (machine := _machine_from_file(path)) is not None
            ]
            nozzle_size = _unique_nozzle_size(resolved)
            machines = [
                machine.model_copy(
                    update={
                        "quality_definition_id": _quality_definition(resolved, machine),
                        "nozzle_diameter_mm": machine.nozzle_diameter_mm or nozzle_size,
                    }
                )
                for machine in raw_machines
            ]
            identifier = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
            installations.append(
                CuraInstallation(
                    installation_id=f"cura-{identifier}",
                    version=candidate.name,
                    channel=channel,
                    data_path=resolved,
                    setting_version=_setting_version(resolved),
                    machines=machines,
                )
            )
    return installations


def _local_name(tag: str) -> str:
    """Return an XML element name without its namespace."""

    return tag.rsplit("}", 1)[-1]


def _material_text(root: Element, path: tuple[str, ...], fallback: str) -> str:
    """Read a bounded namespaced material metadata value by local-name path."""

    current = root
    for name in path:
        matches = [child for child in current if _local_name(child.tag) == name]
        if not matches:
            return fallback
        current = matches[0]
    return (current.text or fallback).strip()[:160]


def _material_from_file(path: Path, installation_id: str) -> CuraMaterial | None:
    """Parse one bounded Cura XML material without retaining its local path."""

    try:
        if path.stat().st_size > 512 * 1024:
            return None
        data = path.read_bytes()
        root = ET.fromstring(data)
    except (OSError, ET.ParseError):
        return None
    if _local_name(root.tag) != "fdmmaterial":
        return None
    brand = _material_text(root, ("metadata", "name", "brand"), "Generic")
    material_type = _material_text(root, ("metadata", "name", "material"), "Unknown")
    color_name = _material_text(root, ("metadata", "name", "color"), "Unknown")
    label = _material_text(root, ("metadata", "name", "label"), color_name)
    guid_text = _material_text(root, ("metadata", "GUID"), "")
    try:
        material_guid = uuid.UUID(guid_text) if guid_text else None
    except ValueError:
        material_guid = None
    settings: dict[str, str | bool] = {}
    settings_element = next(
        (child for child in root if _local_name(child.tag) == "settings"),
        None,
    )
    if settings_element is not None:
        for element in list(settings_element)[:200]:
            key = element.attrib.get("key", "")
            if element.tag.startswith("{") and "ultimaker.com/cura" not in element.tag:
                key = STANDARD_MATERIAL_KEYS.get(key, "")
            if key not in MATERIAL_SETTING_KEYS:
                continue
            value = (element.text or "").strip()
            if len(value) > 500 or "\n" in value or "\r" in value:
                continue
            settings[key] = value == "True" if value in {"True", "False"} else value
    if not settings:
        return None
    content_checksum = hashlib.sha256(
        json.dumps(
            {"material_guid": str(material_guid) if material_guid else None, "settings": settings},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return CuraMaterial(
        source_id=hashlib.sha256(data).hexdigest(),
        installation_id=installation_id,
        name=f"{brand} {material_type} · {label}"[:255],
        brand=brand,
        material_type=material_type,
        color_name=color_name,
        settings=settings,
        material_guid=material_guid,
        content_checksum=content_checksum,
    )


def discover_materials(installations: list[CuraInstallation]) -> list[CuraMaterial]:
    """Discover bounded existing Cura materials for explicit server-side import."""

    materials: list[CuraMaterial] = []
    seen: set[tuple[str, str]] = set()
    for installation in installations:
        for path in sorted((installation.data_path / "materials").glob("*.xml.fdm_material"))[:200]:
            if path.name.startswith("filament_manager_"):
                continue
            material = _material_from_file(path, installation.installation_id)
            if material is None or (material.installation_id, material.source_id) in seen:
                continue
            seen.add((material.installation_id, material.source_id))
            materials.append(material)
    return materials[:500]


def discover_managed_materials(installations: list[CuraInstallation]) -> list[CuraMaterial]:
    """Report bounded known-GUID managed materials for server-side edit detection."""

    materials: list[CuraMaterial] = []
    seen: set[tuple[str, uuid.UUID, str]] = set()
    for installation in installations:
        for path in sorted((installation.data_path / "materials").glob("*.xml.fdm_material"))[:500]:
            if not path.name.startswith("filament_manager_"):
                continue
            material = _material_from_file(path, installation.installation_id)
            if material is None or material.material_guid is None or material.content_checksum is None:
                continue
            identity = (
                material.installation_id,
                material.material_guid,
                material.content_checksum,
            )
            if identity in seen:
                continue
            seen.add(identity)
            materials.append(material)
    return materials[:500]


def unmanaged_material_count(installations: list[CuraInstallation]) -> int:
    """Count user material files that authoritative synchronization would replace."""

    return sum(
        1
        for installation in installations
        for path in (installation.data_path / "materials").glob("*.xml.fdm_material")
        if path.is_file() and not path.name.startswith("filament_manager_")
    )
