"""Bounded decoding and metadata-free storage for untrusted print thumbnails."""

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PRINT_THUMBNAIL_PIXELS = 16_000_000
MAX_PRINT_THUMBNAIL_SIDE = 512


@dataclass(frozen=True, slots=True)
class StoredPrintThumbnail:
    """One normalized print thumbnail safe to retain in PostgreSQL."""

    data: bytes
    media_type: str
    sha256: str
    width: int
    height: int


def sanitize_print_thumbnail(payload: bytes) -> StoredPrintThumbnail:
    """Decode, bound, orient, resize, and re-encode a Moonraker thumbnail as WebP."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as source:
                if source.width * source.height > MAX_PRINT_THUMBNAIL_PIXELS:
                    raise ValueError("Print thumbnail dimensions are too large")
                source.load()
                has_alpha = "A" in source.getbands() or "transparency" in source.info
                image = ImageOps.exif_transpose(source).convert("RGBA" if has_alpha else "RGB")
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
    ) as exc:
        raise ValueError("Moonraker returned an invalid print thumbnail") from exc
    image.thumbnail(
        (MAX_PRINT_THUMBNAIL_SIDE, MAX_PRINT_THUMBNAIL_SIDE),
        Image.Resampling.LANCZOS,
    )
    output = BytesIO()
    image.save(output, format="WEBP", quality=86, method=6)
    data = output.getvalue()
    return StoredPrintThumbnail(
        data=data,
        media_type="image/webp",
        sha256=hashlib.sha256(data).hexdigest(),
        width=image.width,
        height=image.height,
    )
