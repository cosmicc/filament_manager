"""Local authentication primitive tests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from filament_manager.api import dependencies
from filament_manager.api.schemas import ProfileCreate
from filament_manager.config import SecurityConfig
from filament_manager.security import (
    create_session_tokens,
    hash_password,
    hash_token,
    normalize_username,
    validate_password,
    verify_password,
)


def test_usernames_are_nfkc_normalized_and_casefolded() -> None:
    assert normalize_username("  Workshop.Admin  ") == "workshop.admin"


def test_password_length_policy_rejects_short_values() -> None:
    with pytest.raises(ValueError, match="at least 10"):
        validate_password("too-short")


def test_two_character_usernames_are_supported() -> None:
    assert normalize_username(" IP ") == "ip"


def test_argon2id_password_round_trip() -> None:
    encoded = hash_password("correct horse workshop battery")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "correct horse workshop battery") is True
    assert verify_password(encoded, "wrong workshop password") is False


def test_tokens_are_hashed_and_have_bounded_expiry() -> None:
    tokens = create_session_tokens(SecurityConfig(session_lifetime_hours=12, session_idle_minutes=60))
    assert len(tokens.session_token) > 48
    assert len(hash_token(tokens.session_token)) == 64
    assert tokens.created_at.tzinfo is UTC
    assert tokens.created_at <= datetime.now(UTC) < tokens.expires_at
    assert tokens.idle_expires_at < tokens.expires_at


@pytest.mark.asyncio
async def test_active_browser_session_renews_idle_expiry_without_extending_absolute_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ordinary page activity keeps a session alive only inside its fixed boundary."""

    now = datetime.now(UTC)
    absolute_expiry = now + timedelta(days=30)
    browser_session = SimpleNamespace(
        expires_at=absolute_expiry,
        idle_expires_at=now + timedelta(minutes=10),
        last_seen_at=now - timedelta(minutes=6),
        csrf_hash=hash_token("unused-on-get"),
        user=SimpleNamespace(is_active=True, must_change_password=False),
    )

    class Result:
        def scalar_one_or_none(self) -> object:
            return browser_session

    class Session:
        commits = 0

        async def execute(self, _query: object) -> Result:
            return Result()

        async def commit(self) -> None:
            self.commits += 1

    fake_session = Session()
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: SimpleNamespace(security=SimpleNamespace(session_idle_minutes=7 * 24 * 60)),
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/me",
            "headers": [],
            "scheme": "https",
            "server": ("testserver", 443),
        }
    )

    user = await dependencies.current_user(  # type: ignore[arg-type]
        request,
        fake_session,
        session_token="active-session-token",
    )

    assert user is browser_session.user
    assert fake_session.commits == 1
    assert browser_session.idle_expires_at > now + timedelta(days=6)
    assert browser_session.idle_expires_at <= absolute_expiry


def test_cura_extensions_cannot_shadow_typed_or_inject_multiline_settings() -> None:
    base = {
        "filament_product_id": "d1e1d7ce-f0bc-46f5-86b2-d2c74f272f00",
        "printer_id": "312e2722-e60b-467e-8807-cfe410555bee",
        "nozzle_diameter_mm": "0.4",
        "extruder_temp_c": "220",
        "bed_temp_c": "70",
        "flow_percent": "98",
        "cooling_min_percent": "20",
        "cooling_max_percent": "70",
        "filament_density_g_cm3": "1.27",
    }
    with pytest.raises(ValueError, match="reserved"):
        ProfileCreate.model_validate({**base, "cura_extensions": {"speed_print": "999"}})
    with pytest.raises(ValueError, match="invalid text"):
        ProfileCreate.model_validate({**base, "cura_extensions": {"custom_setting": "safe\nunsafe = 1"}})
