"""Remembered filament color identity tests."""

import pytest

from filament_manager.domain.colors import (
    RAINBOW_COLOR_HEXES,
    normalize_color_hex,
    normalize_color_name,
    normalize_color_palette,
)


def test_color_names_are_nfkc_normalized_and_case_insensitive() -> None:
    assert normalize_color_name("  R\uff25D  ") == "red"
    assert normalize_color_name("Temp Sensitive") == "temp sensitive"


def test_empty_color_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="between 1 and 96"):
        normalize_color_name("   ")


def test_color_hex_is_stored_without_hash_in_uppercase() -> None:
    assert normalize_color_hex("#2f80a5") == "2F80A5"
    with pytest.raises(ValueError, match="six hexadecimal"):
        normalize_color_hex("not-a-color")


def test_solid_multicolor_and_rainbow_palettes_are_bounded() -> None:
    assert normalize_color_palette("solid", "#2f80a5", None) == ("solid", ["2F80A5"])
    assert normalize_color_palette("multicolor", None, ["ff0000", "00ff00", "0000ff"]) == (
        "multicolor",
        ["FF0000", "00FF00", "0000FF"],
    )
    assert normalize_color_palette("rainbow", None, None) == (
        "rainbow",
        list(RAINBOW_COLOR_HEXES),
    )
    assert normalize_color_palette("multicolor", None, ["FF0000"]) == (
        "multicolor",
        ["FF0000"],
    )
    with pytest.raises(ValueError, match="one to three"):
        normalize_color_palette("multicolor", None, [])
