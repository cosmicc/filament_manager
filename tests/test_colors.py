"""Remembered filament color identity tests."""

import pytest

from filament_manager.domain.colors import normalize_color_hex, normalize_color_name


def test_color_names_are_nfkc_normalized_and_case_insensitive() -> None:
    assert normalize_color_name("  R\uff25D  ") == "red"
    assert normalize_color_name("Temp Sensitive") == "temp sensitive"


def test_empty_color_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="between 1 and 96"):
        normalize_color_name("   ")


def test_color_hex_is_stored_without_hash_in_uppercase() -> None:
    assert normalize_color_hex("#2f80a5") == "2F80A5"
