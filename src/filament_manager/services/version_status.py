"""Bounded application-version comparison against published GitHub releases."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from time import monotonic

import httpx
import structlog

from filament_manager import __version__

GITHUB_RELEASES_URL = "https://api.github.com/repos/cosmicc/filament_manager/releases"
GITHUB_RELEASE_URL_PREFIX = "https://github.com/cosmicc/filament_manager/releases/tag/"
VERSION_PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
VERSION_CACHE_SECONDS = 900.0

logger = structlog.get_logger()
_cache: tuple[float, VersionStatus] | None = None
_cache_lock = asyncio.Lock()


@dataclass(frozen=True, slots=True)
class VersionStatus:
    """Sanitized running and published release comparison."""

    running_version: str
    latest_version: str | None
    status: str
    release_url: str | None
    detail: str


def _parse_version(value: object) -> tuple[int, int, int] | None:
    """Parse the project's bounded semantic version format."""

    match = VERSION_PATTERN.fullmatch(str(value).strip())
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _comparison_status(running: tuple[int, int, int], latest: tuple[int, int, int]) -> str:
    """Describe the installed release relative to the newest published release."""

    if running == latest:
        return "current"
    return "update_available" if running < latest else "ahead"


async def _fetch_latest_release() -> tuple[str, tuple[int, int, int]]:
    """Return the highest non-draft release, including testing prereleases."""

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"Filament-Manager/{__version__}",
    }
    timeout = httpx.Timeout(4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.get(GITHUB_RELEASES_URL, params={"per_page": 30}, headers=headers)
        response.raise_for_status()
        releases = response.json()
    if not isinstance(releases, list):
        raise ValueError("GitHub releases response was not a list")

    candidates: list[tuple[tuple[int, int, int], str]] = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") is True:
            continue
        tag_name = release.get("tag_name")
        parsed = _parse_version(tag_name)
        if parsed is not None:
            candidates.append((parsed, str(tag_name)))
    if not candidates:
        raise ValueError("GitHub returned no supported published release")
    latest, tag_name = max(candidates)
    return tag_name.removeprefix("v"), latest


async def version_status() -> VersionStatus:
    """Return a cached, sanitized latest-release comparison."""

    global _cache
    now = monotonic()
    if _cache is not None and _cache[0] > now:
        return _cache[1]

    async with _cache_lock:
        now = monotonic()
        if _cache is not None and _cache[0] > now:
            return _cache[1]
        running = _parse_version(__version__)
        try:
            latest_version, latest = await _fetch_latest_release()
            if running is None:
                raise ValueError("Running version has an unsupported format")
            comparison = _comparison_status(running, latest)
            detail = {
                "current": "This installation matches the newest published GitHub release.",
                "update_available": "A newer published GitHub release is available.",
                "ahead": "This installation is newer than the newest published GitHub release.",
            }[comparison]
            result = VersionStatus(
                running_version=__version__,
                latest_version=latest_version,
                status=comparison,
                release_url=f"{GITHUB_RELEASE_URL_PREFIX}v{latest_version}",
                detail=detail,
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            logger.warning("github_version_check_unavailable", error_class=type(exc).__name__)
            result = VersionStatus(
                running_version=__version__,
                latest_version=None,
                status="unavailable",
                release_url=None,
                detail="The latest GitHub release could not be checked safely. Try again later.",
            )
        _cache = (monotonic() + VERSION_CACHE_SECONDS, result)
        return result
