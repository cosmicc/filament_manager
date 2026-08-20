"""Canonical color-name normalization for remembered web samples."""

import re
import unicodedata

RAINBOW_COLOR_HEXES = ("E53935", "FB8C00", "FDD835", "43A047", "1E88E5", "8E24AA")


def normalize_color_name(name: str) -> str:
    """Return the stable case-insensitive identity for a displayed color name."""

    normalized = unicodedata.normalize("NFKC", name).strip().casefold()
    if not 1 <= len(normalized) <= 96:
        raise ValueError("color name must contain between 1 and 96 characters")
    return normalized


def normalize_color_hex(color_hex: str) -> str:
    """Return an uppercase six-character color after schema validation."""

    normalized = color_hex.removeprefix("#").upper()
    if re.fullmatch(r"[0-9A-F]{6}", normalized) is None:
        raise ValueError("color samples must contain exactly six hexadecimal characters")
    return normalized


def normalize_color_palette(
    mode: str,
    color_hex: str | None,
    color_hexes: list[str] | None,
) -> tuple[str, list[str]]:
    """Validate one solid, one/two/three-sample multicolor, or rainbow palette."""

    normalized_mode = mode.strip().casefold()
    supplied = [normalize_color_hex(value) for value in (color_hexes or [])]
    if normalized_mode == "rainbow":
        return "rainbow", list(RAINBOW_COLOR_HEXES)
    if not supplied and (color_hex or normalized_mode == "solid"):
        supplied = [normalize_color_hex(color_hex or "808080")]
    unique = list(dict.fromkeys(supplied))
    if normalized_mode == "solid" and len(unique) == 1:
        return "solid", unique
    if normalized_mode == "multicolor" and 1 <= len(unique) <= 3:
        return "multicolor", unique
    raise ValueError("Solid colors require one sample; multicolor filaments require one to three samples")
