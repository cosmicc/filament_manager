"""Validation, parsing, and natural ordering for build-plate side identifiers."""

import re
from collections.abc import Iterable

MAX_PLATE_CODE_LENGTH = 32
MAX_DISCOVERED_PLATE_SURFACES = 1_000
PLATE_CODE_PATTERN = re.compile(r"P[1-9][0-9]{0,30}\Z")
PLATE_SURFACE_CODE_PATTERN = re.compile(r"(P[1-9][0-9]{0,30})(b?)\Z")


class BuildPlateDiscoveryError(ValueError):
    """Raised when a Moonraker response exceeds safe discovery bounds."""


def is_build_plate_code(value: str) -> bool:
    """Return whether a value is an exact physical ``P<number>`` identifier."""

    return len(value) <= MAX_PLATE_CODE_LENGTH and PLATE_CODE_PATTERN.fullmatch(value) is not None


def is_build_plate_surface_code(value: str) -> bool:
    """Return whether a value is an exact Side A or Side B mesh identifier."""

    return len(value) <= MAX_PLATE_CODE_LENGTH and PLATE_SURFACE_CODE_PATTERN.fullmatch(value) is not None


def split_build_plate_surface_code(value: str) -> tuple[str, str]:
    """Return the physical plate code and side for a canonical surface code."""

    match = PLATE_SURFACE_CODE_PATTERN.fullmatch(value)
    if match is None or len(value) > MAX_PLATE_CODE_LENGTH:
        raise ValueError(f"Invalid build-plate surface code: {value}")
    return match.group(1), "b" if match.group(2) else "a"


def build_plate_sort_key(value: str) -> tuple[int, int, str]:
    """Sort physical and side codes by number, then Side A before Side B."""

    if not is_build_plate_surface_code(value):
        return (2**127, 2, value)
    plate_code, side = split_build_plate_surface_code(value)
    return (int(plate_code[1:]), 1 if side == "b" else 0, value)


def discover_build_plate_surface_codes(
    profile_names: Iterable[str],
) -> tuple[tuple[str, ...], int]:
    """Filter untrusted Moonraker profile names into bounded canonical surface codes."""

    profile_list = tuple(profile_names)
    discovered = {name for name in profile_list if is_build_plate_surface_code(name)}
    if len(discovered) > MAX_DISCOVERED_PLATE_SURFACES:
        raise BuildPlateDiscoveryError(
            f"Moonraker reported more than {MAX_DISCOVERED_PLATE_SURFACES} build-plate meshes"
        )
    ignored_count = sum(not is_build_plate_surface_code(name) for name in profile_list)
    return tuple(sorted(discovered, key=build_plate_sort_key)), ignored_count
