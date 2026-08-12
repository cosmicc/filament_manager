"""Canonical color-name normalization for remembered web samples."""

import unicodedata


def normalize_color_name(name: str) -> str:
    """Return the stable case-insensitive identity for a displayed color name."""

    normalized = unicodedata.normalize("NFKC", name).strip().casefold()
    if not 1 <= len(normalized) <= 96:
        raise ValueError("color name must contain between 1 and 96 characters")
    return normalized


def normalize_color_hex(color_hex: str) -> str:
    """Return an uppercase six-character color after schema validation."""

    return color_hex.removeprefix("#").upper()
