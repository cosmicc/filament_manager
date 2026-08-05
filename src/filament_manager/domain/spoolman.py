"""Spoolman payload helpers that preserve integration-owned fields."""

from typing import Any


def merge_extra_fields(remote_extra: dict[str, Any] | None, managed_extra: dict[str, Any]) -> dict[str, Any]:
    """Merge application-managed keys without erasing unknown remote fields."""

    merged = dict(remote_extra or {})
    merged.update(managed_extra)
    return merged
