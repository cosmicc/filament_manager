"""Bounded Moonraker thumbnail download and sanitized storage tests."""

from io import BytesIO

import httpx
import pytest
import respx
from PIL import Image

from filament_manager.clients.moonraker import MoonrakerClient
from filament_manager.config import PrinterConfig
from filament_manager.services.print_thumbnails import sanitize_print_thumbnail


def _printer_config() -> PrinterConfig:
    """Return one isolated Moonraker endpoint."""

    return PrinterConfig.model_validate(
        {
            "id": "test-printer",
            "name": "Test Printer",
            "base_url": "http://moonraker.test:7125",
            "websocket_url": "ws://moonraker.test:7125/websocket",
            "api_key": "test-api-key",
            "nozzle_diameter_mm": 0.4,
        }
    )


def _png(width: int, height: int) -> bytes:
    """Build one test-only raster image."""

    output = BytesIO()
    Image.new("RGBA", (width, height), (47, 128, 165, 180)).save(output, format="PNG")
    return output.getvalue()


def test_thumbnail_sanitizer_normalizes_dimensions_format_and_metadata() -> None:
    """Untrusted image bytes become one bounded metadata-free WebP."""

    stored = sanitize_print_thumbnail(_png(1200, 600))

    assert stored.media_type == "image/webp"
    assert (stored.width, stored.height) == (512, 256)
    assert len(stored.sha256) == 64
    with Image.open(BytesIO(stored.data)) as image:
        assert image.format == "WEBP"
        assert image.info.get("exif") is None


@respx.mock
@pytest.mark.asyncio
async def test_client_downloads_largest_valid_thumbnail_beneath_gcode_parent() -> None:
    """Moonraker metadata selects the largest safe relative raster path."""

    payload = _png(400, 400)
    route = respx.get("http://moonraker.test:7125/server/files/gcodes/jobs/.thumbs/cube-400x400.png").mock(
        return_value=httpx.Response(200, content=payload)
    )

    result = await MoonrakerClient(_printer_config()).gcode_thumbnail(
        "jobs/cube.gcode",
        {
            "thumbnails": [
                {"width": 32, "height": 32, "size": 100, "relative_path": ".thumbs/small.png"},
                {
                    "width": 400,
                    "height": 400,
                    "size": len(payload),
                    "relative_path": ".thumbs/cube-400x400.png",
                },
            ]
        },
    )

    assert result is not None
    assert result.data == payload
    assert (result.declared_width, result.declared_height) == (400, 400)
    assert route.calls.last.request.headers["X-Api-Key"] == "test-api-key"


@pytest.mark.asyncio
async def test_client_rejects_thumbnail_path_traversal_without_a_request() -> None:
    """A metadata path cannot escape the configured G-code root."""

    result = await MoonrakerClient(_printer_config()).gcode_thumbnail(
        "jobs/cube.gcode",
        {
            "thumbnails": [
                {
                    "width": 400,
                    "height": 400,
                    "size": 100,
                    "relative_path": "../../private.png",
                }
            ]
        },
    )

    assert result is None
