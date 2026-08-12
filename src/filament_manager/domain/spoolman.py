"""Spoolman payload helpers for its JSON-encoded custom-field contract."""

import json
from typing import Any


def merge_extra_fields(remote_extra: dict[str, Any] | None, managed_extra: dict[str, Any]) -> dict[str, Any]:
    """Merge application-managed keys without erasing unknown remote fields."""

    merged = dict(remote_extra or {})
    merged.update(managed_extra)
    return merged


def encode_managed_extra_fields(managed_extra: dict[str, object]) -> dict[str, str]:
    """Encode custom-field values as JSON strings required by Spoolman."""

    return {
        key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        for key, value in managed_extra.items()
    }


def decode_text_extra_field(value: object) -> str | None:
    """Decode one Spoolman text custom field without trusting its shape."""

    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, str) else None
