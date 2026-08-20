"""Tests for scannable spool QR labels and their color indicators."""

from io import BytesIO
from typing import cast

import pytest
from PIL import Image
from qrcode.constants import ERROR_CORRECT_H

from filament_manager.services.spool_labels import (
    QR_BORDER_MODULES,
    build_spool_qr_code,
    render_spool_label_png,
)


def _contains_color(image: Image.Image, color_hex: str, *, tolerance: int = 8) -> bool:
    """Return whether antialiased image pixels contain the requested palette color."""

    expected = tuple(int(color_hex[index : index + 2], 16) for index in (0, 2, 4))
    rgb_image = image.convert("RGB")
    for y_coordinate in range(rgb_image.height):
        for x_coordinate in range(rgb_image.width):
            actual = cast(tuple[int, int, int], rgb_image.getpixel((x_coordinate, y_coordinate)))
            if all(abs(actual[channel] - expected[channel]) <= tolerance for channel in range(3)):
                return True
    return False


def test_spool_qr_uses_high_error_correction_and_standard_quiet_zone() -> None:
    """Reserve enough recovery and whitespace for a safely embedded center icon."""

    url = "https://filament.example.test/spools/00000000-0000-4000-8000-000000000001"
    qr_code = build_spool_qr_code(url)

    assert qr_code.error_correction == ERROR_CORRECT_H
    assert qr_code.border == QR_BORDER_MODULES == 4
    assert qr_code.modules_count > 0


@pytest.mark.parametrize(
    ("mode", "primary", "colors", "expected_colors"),
    [
        ("solid", "2F80A5", ["2F80A5"], ["2F80A5"]),
        ("multicolor", "E53935", ["E53935", "FDD835", "1E88E5"], ["E53935", "FDD835", "1E88E5"]),
        ("rainbow", "E53935", [], ["E53935", "FDD835", "1E88E5", "8E24AA"]),
    ],
)
def test_spool_label_png_embeds_the_canonical_palette(
    mode: str,
    primary: str,
    colors: list[str],
    expected_colors: list[str],
) -> None:
    """Render each palette mode in a square PNG without disturbing the quiet zone."""

    payload = render_spool_label_png(
        "https://filament.example.test/spools/00000000-0000-4000-8000-000000000001",
        color_mode=mode,
        color_hex=primary,
        color_hexes=colors,
    )
    image = Image.open(BytesIO(payload))

    assert image.format == "PNG"
    assert image.mode == "RGB"
    assert image.width == image.height
    assert image.getpixel((0, 0)) == (255, 255, 255)
    for expected_color in expected_colors:
        assert _contains_color(image, expected_color)
