"""Sanitized GitHub release comparison tests."""

import httpx
import pytest
import respx

from filament_manager.services import version_status as version_service


@respx.mock
@pytest.mark.asyncio
async def test_version_status_includes_prereleases_and_caches_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The newest non-draft semantic release is compared without repeat requests."""

    monkeypatch.setattr(version_service, "_cache", None)
    route = respx.get(version_service.GITHUB_RELEASES_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"tag_name": "v9.0.0", "draft": True, "prerelease": False},
                {"tag_name": "v0.5.3", "draft": False, "prerelease": True},
                {"tag_name": "v0.5.3", "draft": False, "prerelease": False},
                {"tag_name": "not-a-version", "draft": False, "prerelease": False},
            ],
        )
    )

    first = await version_service.version_status()
    second = await version_service.version_status()

    assert first.running_version == "0.5.3"
    assert first.latest_version == "0.5.3"
    assert first.status == "current"
    assert first.release_url == "https://github.com/cosmicc/filament_manager/releases/tag/v0.5.3"
    assert second == first
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_version_status_returns_bounded_unavailable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub failures never expose an upstream response body to the web UI."""

    monkeypatch.setattr(version_service, "_cache", None)
    respx.get(version_service.GITHUB_RELEASES_URL).mock(
        return_value=httpx.Response(503, text="sensitive upstream diagnostics")
    )

    result = await version_service.version_status()

    assert result.status == "unavailable"
    assert result.latest_version is None
    assert result.release_url is None
    assert "sensitive" not in result.detail
