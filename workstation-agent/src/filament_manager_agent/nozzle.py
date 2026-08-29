"""Safely select an existing Cura nozzle variant for an exact local machine."""

import configparser
import json
import os
import re
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .apply import _atomic_write, _deployment_key, _safe_target
from .config import data_path
from .machine_settings import apply_managed_machine_gcode, serialize_cura_config
from .models import CuraInstallation, CuraMachine


def _parser(path: Path) -> configparser.ConfigParser | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024:
            return None
        parser.read(path, encoding="utf-8")
    except (OSError, UnicodeError, configparser.Error):
        return None
    return parser


def _normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _matching_machine(installation: CuraInstallation, payload: dict[str, object]) -> CuraMachine | None:
    identities = {_normalized(payload.get("printer_code")), _normalized(payload.get("printer_name"))}
    identities.discard("")
    matches = [
        machine
        for machine in installation.machines
        if identities.intersection(
            {
                _normalized(machine.machine_id),
                _normalized(machine.display_name),
                _normalized(machine.definition_id),
            }
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _matching_variant(
    installation: CuraInstallation,
    definition_id: str,
    diameter: Decimal,
) -> tuple[Path, str] | None:
    candidates: dict[str, Path] = {}
    expected_definition = _normalized(definition_id)
    for variants in _variant_directories(installation):
        for path in sorted(variants.glob("*.cfg"))[:5000]:
            parser = _parser(path)
            if parser is None or not parser.has_section("values"):
                continue
            metadata = parser["metadata"] if parser.has_section("metadata") else {}
            if str(metadata.get("type", "")).casefold() != "variant":
                continue
            if str(metadata.get("hardware_type", "")).casefold() != "nozzle":
                continue
            if _decimal(parser["values"].get("machine_nozzle_size")) != diameter:
                continue
            general = parser["general"] if parser.has_section("general") else {}
            definition = _normalized(general.get("definition"))
            if expected_definition and definition and definition != expected_definition:
                continue
            variant_id = path.name.removesuffix(".inst.cfg").removesuffix(".cfg")
            candidates.setdefault(variant_id, path)
    if len(candidates) != 1:
        return None
    variant_id, path = next(iter(candidates.items()))
    return path, variant_id


def _matching_extruder(
    installation: CuraInstallation,
    machine: CuraMachine,
) -> tuple[Path, configparser.ConfigParser, str, str] | None:
    """Return the exact enabled position-zero extruder linked to one machine."""

    identities = {_normalized(machine.machine_id), _normalized(machine.display_name)}
    identities.discard("")
    candidates: list[tuple[Path, configparser.ConfigParser, str, str]] = []
    directory = installation.data_path / "extruders"
    if not directory.is_dir() or directory.is_symlink():
        return None
    for path in sorted(directory.glob("*.cfg"))[:500]:
        parser = _parser(path)
        if parser is None or not parser.has_section("metadata") or not parser.has_section("containers"):
            continue
        metadata = parser["metadata"]
        if str(metadata.get("type", "")).casefold() != "extruder_train":
            continue
        if str(metadata.get("position", "")).strip() != "0":
            continue
        if str(metadata.get("enabled", "true")).casefold() in {"false", "0", "no"}:
            continue
        if _normalized(metadata.get("machine")) not in identities:
            continue
        settings_id = str(parser["containers"].get("6") or "").strip()
        definition_id = str(parser["containers"].get("7") or "").strip()
        if not settings_id or not definition_id:
            continue
        candidates.append((path, parser, settings_id, definition_id))
    return candidates[0] if len(candidates) == 1 else None


def _matching_definition_change(
    installation: CuraInstallation,
    settings_id: str,
    definition_id: str,
) -> tuple[Path, configparser.ConfigParser] | None:
    """Resolve the existing definition-change container selected by an extruder."""

    candidates: list[tuple[Path, configparser.ConfigParser]] = []
    directory = installation.data_path / "definition_changes"
    if not directory.is_dir() or directory.is_symlink():
        return None
    for path in sorted(directory.glob("*.cfg"))[:500]:
        parser = _parser(path)
        if parser is None or not parser.has_section("general"):
            continue
        general = parser["general"]
        metadata = parser["metadata"] if parser.has_section("metadata") else {}
        if str(metadata.get("type", "")).casefold() != "definition_changes":
            continue
        if str(general.get("name") or "").strip() != settings_id:
            continue
        if _normalized(general.get("definition")) != _normalized(definition_id):
            continue
        candidates.append((path, parser))
    return candidates[0] if len(candidates) == 1 else None


def linked_extruder_nozzle_diameter(
    installation: CuraInstallation,
    machine: CuraMachine,
) -> str | None:
    """Read the exact linked position-zero extruder's effective saved nozzle size."""

    extruder = _matching_extruder(installation, machine)
    if extruder is None:
        return None
    _, _, settings_id, definition_id = extruder
    definition_change = _matching_definition_change(installation, settings_id, definition_id)
    if definition_change is None:
        return None
    _, parser = definition_change
    if not parser.has_section("values"):
        return None
    diameter = _decimal(parser["values"].get("machine_nozzle_size"))
    if diameter is None or not diameter.is_finite() or diameter <= 0:
        return None
    return format(diameter, "f")


def _variant_directories(installation: CuraInstallation) -> list[Path]:
    """Return bounded, existing Cura variant roots without searching the workstation broadly."""

    directories = [installation.data_path / "variants"]
    override = os.environ.get("FILAMENT_MANAGER_CURA_RESOURCE_ROOTS")
    if override:
        directories.extend(
            Path(value).expanduser() / "variants" for value in override.split(os.pathsep) if value
        )
    home = Path.home()
    if sys.platform == "win32":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if not root:
                continue
            for application in sorted(Path(root).glob("UltiMaker Cura*"))[:20]:
                directories.append(application / "share" / "cura" / "resources" / "variants")
    else:
        directories.extend(
            [
                Path("/usr/share/cura/resources/variants"),
                Path("/usr/share/ultimaker-cura/resources/variants"),
                Path("/app/share/cura/resources/variants"),
                Path("/snap/cura/current/usr/share/cura/resources/variants"),
                Path("/snap/cura-slicer/current/usr/share/cura/resources/variants"),
                home
                / ".local/share/flatpak/app/com.ultimaker.cura/current/active/files/share/cura"
                / "resources/variants",
                Path(
                    "/var/lib/flatpak/app/com.ultimaker.cura/current/active/files/share/cura/resources/variants"
                ),
            ]
        )
    safe_directories: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        try:
            resolved = directory.resolve(strict=True)
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        safe_directories.append(resolved)
    return safe_directories


def apply_nozzle_update(
    installation: CuraInstallation,
    deployment_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Back up and align one exact machine and its linked position-zero extruder."""

    deployment_key = _deployment_key(deployment_id)
    target_diameter = _decimal(payload.get("nozzle_diameter_mm"))
    if target_diameter is None or target_diameter <= 0:
        raise RuntimeError("The requested Cura nozzle diameter is invalid.")
    machine = _matching_machine(installation, payload)
    if machine is None:
        raise RuntimeError("No single matching Cura printer was found for the nozzle update.")
    extruder = _matching_extruder(installation, machine)
    if extruder is None:
        raise RuntimeError("No single linked Cura position-zero extruder was found for the nozzle update.")
    extruder_path, extruder_parser, settings_id, definition_id = extruder
    definition_change = _matching_definition_change(
        installation,
        settings_id,
        definition_id,
    )
    if definition_change is None:
        raise RuntimeError(
            "No single linked Cura extruder settings container was found for the nozzle update."
        )
    definition_change_path, definition_change_parser = definition_change
    variant = _matching_variant(installation, definition_id, target_diameter)
    variant_id = variant[1] if variant is not None else None
    try:
        relative_target = machine.source_path.relative_to(installation.data_path)
    except ValueError as error:
        raise RuntimeError("The matching Cura printer configuration is outside its installation.") from error
    machine_target = _safe_target(installation.data_path, relative_target)
    machine_parser = _parser(machine_target)
    if machine_parser is None:
        raise RuntimeError("The matching Cura printer configuration is unsafe or invalid.")
    if not machine_parser.has_section("metadata"):
        machine_parser.add_section("metadata")
    machine_parser["metadata"]["nozzle_diameter"] = format(target_diameter, "f")
    apply_managed_machine_gcode(machine_parser)
    if variant_id is not None:
        extruder_parser["containers"]["5"] = variant_id
    if not definition_change_parser.has_section("values"):
        definition_change_parser.add_section("values")
    definition_change_parser["values"]["machine_nozzle_size"] = format(target_diameter, "f")

    targets = {
        machine_target: serialize_cura_config(machine_parser),
        _safe_target(
            installation.data_path,
            extruder_path.relative_to(installation.data_path),
        ): serialize_cura_config(extruder_parser),
        _safe_target(
            installation.data_path,
            definition_change_path.relative_to(installation.data_path),
        ): serialize_cura_config(definition_change_parser),
    }
    originals = {target: target.read_bytes() for target in targets}
    backup_directory = data_path() / "nozzle-backups" / deployment_key
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / f"{installation.installation_id}.zip"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for target, content in originals.items():
            archive.writestr(target.relative_to(installation.data_path).as_posix(), content)
        archive.writestr(
            ".filament-manager-nozzle-backup.json",
            json.dumps(
                {
                    "machine_id": machine.machine_id,
                    "extruder_definition_id": definition_id,
                    "variant_id": variant_id,
                },
                sort_keys=True,
            ),
        )
    try:
        for target, content in targets.items():
            _atomic_write(target, content)
    except Exception:
        for target, content in originals.items():
            _atomic_write(target, content)
        raise
    return {
        "installation_id": installation.installation_id,
        "version": installation.version,
        "machine_id": machine.machine_id,
        "extruder_definition_id": definition_id,
        "nozzle_diameter_mm": format(target_diameter, "f"),
        "variant_id": variant_id,
        "backup_id": f"{deployment_key}/{installation.installation_id}",
    }
