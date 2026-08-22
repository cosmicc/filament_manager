"""Safely select an existing Cura nozzle variant for an exact local machine."""

import configparser
import io
import json
import os
import re
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .apply import _atomic_write, _deployment_key, _safe_target
from .config import data_path
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
    except (InvalidOperation, ValueError):
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
    machine: CuraMachine,
    diameter: Decimal,
) -> tuple[Path, str] | None:
    candidates: dict[str, Path] = {}
    machine_definition = _normalized(machine.definition_id)
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
            if machine_definition and definition and definition != machine_definition:
                continue
            variant_id = path.name.removesuffix(".inst.cfg").removesuffix(".cfg")
            candidates.setdefault(variant_id, path)
    if len(candidates) != 1:
        return None
    variant_id, path = next(iter(candidates.items()))
    return path, variant_id


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
    """Back up and update one exact machine only when a matching variant already exists."""

    deployment_key = _deployment_key(deployment_id)
    target_diameter = _decimal(payload.get("nozzle_diameter_mm"))
    if target_diameter is None or target_diameter <= 0:
        raise RuntimeError("The requested Cura nozzle diameter is invalid.")
    machine = _matching_machine(installation, payload)
    if machine is None:
        raise RuntimeError("No single matching Cura printer was found for the nozzle update.")
    variant = _matching_variant(installation, machine, target_diameter)
    if variant is None:
        raise RuntimeError(
            "Cura does not have one existing matching nozzle variant for this printer and diameter."
        )
    _, variant_id = variant
    try:
        relative_target = machine.source_path.relative_to(installation.data_path)
    except ValueError as error:
        raise RuntimeError("The matching Cura printer configuration is outside its installation.") from error
    target = _safe_target(installation.data_path, relative_target)
    parser = _parser(target)
    if parser is None:
        raise RuntimeError("The matching Cura printer configuration is unsafe or invalid.")
    if not parser.has_section("metadata"):
        parser.add_section("metadata")
    if not parser.has_section("containers"):
        parser.add_section("containers")
    parser["metadata"]["nozzle_diameter"] = format(target_diameter, "f")
    parser["metadata"]["variant"] = variant_id
    parser["containers"]["5"] = variant_id
    output = io.StringIO()
    parser.write(output, space_around_delimiters=True)
    backup_directory = data_path() / "nozzle-backups" / deployment_key
    backup_directory.mkdir(parents=True, exist_ok=True)
    backup_path = backup_directory / f"{installation.installation_id}.zip"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(target.name, target.read_bytes())
        archive.writestr(
            ".filament-manager-nozzle-backup.json",
            json.dumps({"machine_id": machine.machine_id, "variant_id": variant_id}, sort_keys=True),
        )
    _atomic_write(target, output.getvalue().encode("utf-8"))
    return {
        "installation_id": installation.installation_id,
        "version": installation.version,
        "machine_id": machine.machine_id,
        "nozzle_diameter_mm": format(target_diameter, "f"),
        "variant_id": variant_id,
        "backup_id": f"{deployment_key}/{installation.installation_id}",
    }
