"""Cura process, user-data, version, and machine-instance discovery."""

import configparser
import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element

import psutil
from defusedxml import ElementTree as ET

from .models import CuraInstallation, CuraMachine, CuraMaterial

VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+){1,3}$")
SETTING_VERSION_PATTERN = re.compile(r"^\s*setting_version\s*=\s*(\d+)\s*$", re.MULTILINE)
MATERIAL_SETTING_KEYS = frozenset(
    {
        "acceleration_enabled",
        "acceleration_infill",
        "acceleration_print",
        "acceleration_roofing",
        "acceleration_support",
        "acceleration_topbottom",
        "acceleration_travel",
        "acceleration_travel_enabled",
        "acceleration_wall",
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
        "hole_xy_offset",
        "hole_xy_offset_max_diameter",
        "ironing_enabled",
        "ironing_flow",
        "ironing_line_spacing",
        "ironing_speed",
        "klipper_pressure_advance_factor",
        "klipper_smooth_time_enable",
        "klipper_smooth_time_factor",
        "limit_support_retractions",
        "material_bed_temperature",
        "material_flow",
        "material_print_temperature",
        "retract_at_layer_change",
        "retraction_amount",
        "retraction_enable",
        "retraction_min_travel",
        "retraction_prime_speed",
        "retraction_retract_speed",
        "retraction_speed",
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
        "xy_offset",
        "xy_offset_layer_0",
    }
)
STANDARD_MATERIAL_KEYS = {
    "build volume temperature": "build_volume_temperature",
    "heated bed temperature": "material_bed_temperature",
    "print cooling": "cool_fan_speed",
    "print temperature": "material_print_temperature",
    "retraction amount": "retraction_amount",
    "retraction speed": "retraction_speed",
}
QUALITY_PROFILE_FILE_LIMIT = 200
QUALITY_PROFILE_MAX_BYTES = 512 * 1024
QUALITY_EXTRUDER_STEM = re.compile(
    r"^(?P<machine>.+)_extruder_(?P<position>\d+)_(?:%23|#)\d+_(?P<profile>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _QualityProfilePart:
    """One bounded global or extruder-specific Cura quality-change layer."""

    identity: str
    name: str
    quality_type: str | None
    position: int | None
    settings: dict[str, str | bool]
    omitted_keys: frozenset[str]


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


def _candidate_roots() -> list[tuple[str, Path, Path]]:
    override = os.environ.get("FILAMENT_MANAGER_CURA_ROOTS")
    if override:
        return [
            ("Configured Cura", Path(value).expanduser(), Path(value).expanduser())
            for value in override.split(os.pathsep)
            if value
        ]
    home = Path.home()
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return [("Windows Cura", appdata / "cura", appdata / "cura")]
    return [
        ("Linux Cura", home / ".local" / "share" / "cura", home / ".config" / "cura"),
        (
            "Flatpak Cura",
            home / ".var" / "app" / "com.ultimaker.cura" / "data" / "cura",
            home / ".var" / "app" / "com.ultimaker.cura" / "config" / "cura",
        ),
        (
            "Snap Cura",
            home / "snap" / "cura-slicer" / "current" / ".local" / "share" / "cura",
            home / "snap" / "cura-slicer" / "current" / ".config" / "cura",
        ),
        (
            "Snap Cura",
            home / "snap" / "cura" / "current" / ".local" / "share" / "cura",
            home / "snap" / "cura" / "current" / ".config" / "cura",
        ),
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
    for channel, root, config_root in _candidate_roots():
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
                    config_path=(
                        (
                            config_root
                            if VERSION_PATTERN.match(config_root.name)
                            else config_root / candidate.name
                        )
                        .expanduser()
                        .resolve(strict=False)
                    ),
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
        if path.is_symlink() or path.stat().st_size > 512 * 1024:
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


def _quality_profile_identity(path: Path, position: int | None) -> str | None:
    """Return the matching global-profile stem for one Cura quality-change file."""

    stem = path.name.removesuffix(".inst.cfg")
    if position is None:
        return stem
    match = QUALITY_EXTRUDER_STEM.fullmatch(stem)
    if match is None or int(match.group("position")) != position:
        return None
    return f"{match.group('machine')}_{match.group('profile')}"


def _quality_profile_part(path: Path) -> _QualityProfilePart | None:
    """Parse one bounded quality-change layer without evaluating Cura expressions."""

    try:
        if path.is_symlink() or path.stat().st_size > QUALITY_PROFILE_MAX_BYTES:
            return None
    except OSError:
        return None
    parser = _read_cfg(path)
    if (
        parser is None
        or not parser.has_section("general")
        or not parser.has_section("metadata")
        or not parser.has_section("values")
        or parser["metadata"].get("type") != "quality_changes"
    ):
        return None
    raw_position = str(parser["metadata"].get("position") or "").strip()
    if raw_position:
        try:
            position = int(raw_position)
        except ValueError:
            return None
        # Filament Manager currently supports one printer/nozzle extrusion path.
        if position != 0:
            return None
    else:
        position = None
    identity = _quality_profile_identity(path, position)
    name = str(parser["general"].get("name") or "").strip()[:255]
    if identity is None or not name:
        return None
    settings: dict[str, str | bool] = {}
    omitted_keys: set[str] = set()
    for key, raw_value in parser["values"].items():
        if key not in MATERIAL_SETTING_KEYS:
            continue
        value = str(raw_value).strip()
        if not value or len(value) > 500 or "\n" in value or "\r" in value:
            continue
        # Cura expressions require its runtime context. Importing or evaluating them
        # server-side would be unsafe and could produce a misleading resolved value.
        if value.startswith("="):
            omitted_keys.add(key)
            continue
        settings[key] = value == "True" if value in {"True", "False"} else value
    return _QualityProfilePart(
        identity=identity,
        name=name,
        quality_type=str(parser["metadata"].get("quality_type") or "").strip()[:96] or None,
        position=position,
        settings=settings,
        omitted_keys=frozenset(omitted_keys),
    )


def _profile_machine(installation: CuraInstallation, identity: str) -> CuraMachine | None:
    """Match a quality-profile filename prefix to one discovered Cura machine."""

    normalized_identity = re.sub(r"[^a-z0-9]", "", identity.casefold())
    ranked: list[tuple[int, CuraMachine]] = []
    for machine in installation.machines:
        matches = [
            re.sub(r"[^a-z0-9]", "", value.casefold())
            for value in (machine.definition_id, machine.machine_id, machine.display_name)
            if value
        ]
        score = max(
            (len(value) for value in matches if value and normalized_identity.startswith(value)),
            default=0,
        )
        if score:
            ranked.append((score, machine))
    if ranked:
        ranked.sort(key=lambda item: item[0], reverse=True)
        if len(ranked) == 1 or ranked[0][0] > ranked[1][0]:
            return ranked[0][1]
    return installation.machines[0] if len(installation.machines) == 1 else None


def discover_print_profiles(installations: list[CuraInstallation]) -> list[CuraMaterial]:
    """Discover saved Cura print profiles as bounded, approved import sources."""

    profiles: list[CuraMaterial] = []
    seen: set[tuple[str, str]] = set()
    for installation in installations:
        global_parts: dict[str, _QualityProfilePart] = {}
        extruder_parts: dict[str, _QualityProfilePart] = {}
        quality_paths = sorted((installation.data_path / "quality_changes").glob("*.cfg"))[
            :QUALITY_PROFILE_FILE_LIMIT
        ]
        for path in quality_paths:
            part = _quality_profile_part(path)
            if part is None:
                continue
            target = global_parts if part.position is None else extruder_parts
            target.setdefault(part.identity, part)
        for identity in sorted(set(global_parts) | set(extruder_parts)):
            global_part = global_parts.get(identity)
            extruder_part = extruder_parts.get(identity)
            settings = dict(global_part.settings if global_part else {})
            omitted_keys = set(global_part.omitted_keys if global_part else ())
            if extruder_part is not None:
                for key in extruder_part.omitted_keys:
                    settings.pop(key, None)
                    omitted_keys.add(key)
                for key, value in extruder_part.settings.items():
                    settings[key] = value
                    omitted_keys.discard(key)
            source_part = extruder_part or global_part
            assert source_part is not None
            source_payload = json.dumps(
                {
                    "source_kind": "print_profile",
                    "installation_id": installation.installation_id,
                    "identity": identity,
                    "name": source_part.name,
                    "quality_type": source_part.quality_type,
                    "settings": settings,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            source_id = hashlib.sha256(source_payload).hexdigest()
            if (installation.installation_id, source_id) in seen:
                continue
            seen.add((installation.installation_id, source_id))
            machine = _profile_machine(installation, identity)
            profiles.append(
                CuraMaterial(
                    source_id=source_id,
                    installation_id=installation.installation_id,
                    source_kind="print_profile",
                    name=source_part.name,
                    brand="Cura print profile",
                    material_type="Not assigned",
                    color_name="Not applicable",
                    settings=settings,
                    machine_name=machine.display_name if machine else None,
                    quality_type=source_part.quality_type,
                    omitted_setting_count=len(omitted_keys),
                )
            )
    return profiles[:500]


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
