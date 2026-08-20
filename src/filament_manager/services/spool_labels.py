"""Render scannable spool QR labels with a canonical color indicator."""

from io import BytesIO
from typing import Final

import qrcode
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H
from qrcode.image.pil import PilImage

from filament_manager.domain.colors import normalize_color_palette

QR_BOX_SIZE: Final = 10
QR_BORDER_MODULES: Final = 4
SPOOL_ICON_MODULE_FRACTION: Final = 0.30
SPOOL_ICON_MINIMUM_MODULES: Final = 7
SPOOL_ICON_BACKING_MODULES: Final = 1
SPOOL_ICON_SUPERSAMPLING: Final = 4


def _rgb(color_hex: str) -> tuple[int, int, int]:
    """Convert one validated six-character hexadecimal color to RGB."""

    return (
        int(color_hex[0:2], 16),
        int(color_hex[2:4], 16),
        int(color_hex[4:6], 16),
    )


def _mixed_with_white(color: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    """Mix an RGB color with white using the same visual balance as the web swatch."""

    return (
        round(color[0] * ratio + 255 * (1 - ratio)),
        round(color[1] * ratio + 255 * (1 - ratio)),
        round(color[2] * ratio + 255 * (1 - ratio)),
    )


def _palette_image(size: int, mode: str, color_hexes: list[str]) -> Image.Image:
    """Draw the solid, segmented, or continuous rainbow filament fill."""

    colors = [_rgb(value) for value in color_hexes]
    image = Image.new("RGB", (size, size), colors[0])
    if mode == "solid":
        return image

    draw = ImageDraw.Draw(image)
    bounds = (0, 0, size - 1, size - 1)
    if mode == "multicolor":
        for index, color in enumerate(colors):
            start = -90 + (360 * index / len(colors))
            end = -90 + (360 * (index + 1) / len(colors))
            draw.pieslice(bounds, start=start, end=end, fill=color)
        return image

    # The browser uses a continuous conic rainbow. Drawing one-degree wedges
    # preserves that appearance while keeping the resulting label self-contained.
    for degree in range(360):
        position = degree / 360 * len(colors)
        first_index = int(position) % len(colors)
        second_index = (first_index + 1) % len(colors)
        blend = position - int(position)
        color = (
            round(colors[first_index][0] * (1 - blend) + colors[second_index][0] * blend),
            round(colors[first_index][1] * (1 - blend) + colors[second_index][1] * blend),
            round(colors[first_index][2] * (1 - blend) + colors[second_index][2] * blend),
        )
        draw.pieslice(bounds, start=degree - 90, end=degree - 89, fill=color)
    return image


def _spool_icon(size: int, mode: str, color_hexes: list[str]) -> Image.Image:
    """Render the shared physical spool silhouette as an antialiased RGBA image."""

    render_size = size * SPOOL_ICON_SUPERSAMPLING
    palette = _palette_image(render_size, mode, color_hexes)
    icon = Image.new("RGBA", (render_size, render_size), (255, 255, 255, 0))
    circle_mask = Image.new("L", (render_size, render_size), 0)
    ImageDraw.Draw(circle_mask).ellipse((0, 0, render_size - 1, render_size - 1), fill=255)
    icon.paste(palette, (0, 0), circle_mask)

    draw = ImageDraw.Draw(icon)
    center = render_size / 2
    radius = render_size / 2

    def circle_bounds(scale: float) -> tuple[int, int, int, int]:
        circle_radius = radius * scale
        return (
            round(center - circle_radius),
            round(center - circle_radius),
            round(center + circle_radius),
            round(center + circle_radius),
        )

    # Match the web spool silhouette: a white hub and a white structural ring
    # leave the selected filament palette visible in the inner and outer bands.
    draw.ellipse(circle_bounds(0.68), fill="white")
    inner_mask = Image.new("L", (render_size, render_size), 0)
    ImageDraw.Draw(inner_mask).ellipse(circle_bounds(0.58), fill=255)
    icon.paste(palette, (0, 0), inner_mask)
    draw.ellipse(circle_bounds(0.27), fill="white")

    border_color = _mixed_with_white(_rgb(color_hexes[0]), 0.60)
    draw.ellipse(
        (0, 0, render_size - 1, render_size - 1),
        outline=border_color,
        width=max(SPOOL_ICON_SUPERSAMPLING, round(render_size * 0.07)),
    )
    return icon.resize((size, size), Image.Resampling.LANCZOS)


def _odd_module_count(module_count: int) -> int:
    """Return a centered odd icon size near the conservative target fraction."""

    requested = max(SPOOL_ICON_MINIMUM_MODULES, round(module_count * SPOOL_ICON_MODULE_FRACTION))
    return requested if requested % 2 else requested + 1


def build_spool_qr_code(url: str) -> qrcode.QRCode[PilImage]:
    """Build a stable URL QR code with enough recovery for a small center icon."""

    qr_code: qrcode.QRCode[PilImage] = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=QR_BOX_SIZE,
        border=QR_BORDER_MODULES,
        image_factory=PilImage,
    )
    qr_code.add_data(url)
    qr_code.make(fit=True)
    return qr_code


def render_spool_label_png(
    url: str,
    *,
    color_mode: str,
    color_hex: str | None,
    color_hexes: list[str],
) -> bytes:
    """Return a PNG QR code containing a conservative centered spool-color icon."""

    normalized_mode, normalized_colors = normalize_color_palette(
        color_mode,
        color_hex,
        color_hexes,
    )
    qr_code = build_spool_qr_code(url)
    qr_image = qr_code.make_image(fill_color="black", back_color="white")
    image = qr_image.get_image().convert("RGB")

    icon_modules = _odd_module_count(qr_code.modules_count)
    icon_size = icon_modules * QR_BOX_SIZE
    backing_size = icon_size + (2 * SPOOL_ICON_BACKING_MODULES * QR_BOX_SIZE)
    backing_offset = (image.width - backing_size) // 2
    backing_end = backing_offset + backing_size - 1
    ImageDraw.Draw(image).rectangle(
        (backing_offset, backing_offset, backing_end, backing_end),
        fill="white",
    )

    icon = _spool_icon(icon_size, normalized_mode, normalized_colors)
    icon_offset = (image.width - icon_size) // 2
    image.paste(icon, (icon_offset, icon_offset), icon)

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
