"""Bounded original-file archive reads; never execute or rewrite G-code."""

import hashlib
import zlib

from filament_manager.models.printing import PrintGcodeArchive

MAX_ARCHIVE_BYTES = 100_000_000
GCODE_PAGE_BYTES = 32_768


def archive_bytes(archive: PrintGcodeArchive) -> bytes:
    """Validate a single bounded zlib stream before serving its original bytes."""
    if not 0 <= archive.size_bytes <= MAX_ARCHIVE_BYTES:
        raise ValueError("Invalid saved G-code size")
    if len(archive.compressed_data) > MAX_ARCHIVE_BYTES + 1_000_000:
        raise ValueError("Invalid compressed G-code size")
    decoder = zlib.decompressobj()
    try:
        data = decoder.decompress(archive.compressed_data, archive.size_bytes + 1)
    except zlib.error as error:
        raise ValueError("Invalid saved G-code") from error
    if (
        len(data) != archive.size_bytes
        or not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
        or hashlib.sha256(data).hexdigest() != archive.sha256
    ):
        raise ValueError("Saved G-code failed validation")
    return data
