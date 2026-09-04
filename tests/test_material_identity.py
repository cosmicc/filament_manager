"""Canonical live labels stay derived without changing legacy stored identities."""

import pytest

from filament_manager.models.inventory import FilamentProduct


@pytest.mark.parametrize(
    ("filler", "finish", "expected"),
    [
        (None, None, "PLA · Blue"),
        (" sTaNdArD ", "Standard", "PLA · Blue"),
        ("None", " No finish ", "PLA · Blue"),
        ("Not specified", "Matte", "PLA · Blue · Matte"),
        ("Carbon Fiber", "Silk", "PLA · Blue · Carbon Fiber · Silk"),
    ],
)
def test_live_name_ignores_legacy_display_name(filler: str | None, finish: str | None, expected: str) -> None:
    product = FilamentProduct(
        material_type="PLA",
        color_name="Blue",
        filler=filler,
        finish=finish,
        product_name="Legacy brand-specific name",
    )
    assert product.display_name == expected
    assert product.product_name == "Legacy brand-specific name"


def test_maximum_derived_name_fits_response_contract() -> None:
    product = FilamentProduct(
        material_type="M" * 48,
        color_name="C" * 96,
        filler="F" * 96,
        finish="S" * 96,
    )
    assert len(product.display_name) == 345
