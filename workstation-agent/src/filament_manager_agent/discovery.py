"""Cura process, user-data, version, and machine-instance discovery."""

import configparser
import hashlib
import os
import re
import sys
from pathlib import Path

import psutil

from .models import CuraInstallation, CuraMachine

VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+){1,3}$")
SETTING_VERSION_PATTERN = re.compile(r"^\s*setting_version\s*=\s*(\d+)\s*$", re.MULTILINE)


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
