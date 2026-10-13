"""Verified discoverable passkey login and password-confirmed account enrollment."""

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import exceptions as webauthn_errors
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from filament_manager.api.dependencies import SESSION_COOKIE, Administrator, DatabaseSession
from filament_manager.api.errors import ApiError
from filament_manager.api.schemas import LoginResponse
from filament_manager.config import get_settings
from filament_manager.models.auth import User, UserSession
from filament_manager.models.passkeys import Passkey, PasskeyChallenge
from filament_manager.security import hash_token, verify_password
from filament_manager.services.browser_sessions import issue_browser_session
from filament_manager.services.events import add_audit_event

from .auth import LoginRateLimiter

router = APIRouter(prefix="/auth/passkeys", tags=["authentication"])
passkey_limiter = LoginRateLimiter(attempts=24)
CEREMONY_SECONDS = 300
MAX_PASSKEYS = 20
# These parsing/verification errors are expected untrusted-input refusals. Never
# return their messages, credential bytes, or upstream exception details.
VERIFICATION_ERRORS = (
    ValueError,
    TypeError,
    KeyError,
    OverflowError,
    webauthn_errors.InvalidAuthenticationResponse,
    webauthn_errors.InvalidRegistrationResponse,
    webauthn_errors.InvalidJSONStructure,
    webauthn_errors.InvalidCBORData,
    webauthn_errors.InvalidAttestationObjectStructure,
    webauthn_errors.InvalidAuthenticatorDataStructure,
    webauthn_errors.InvalidPublicKeyStructure,
    webauthn_errors.InvalidBackupFlags,
)


class PasswordConfirmation(BaseModel):
    """Bound password confirmation; never persist or echo this submitted value."""

    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)


class Enrollment(PasswordConfirmation):
    """An operator-supplied friendly label for one new authenticator."""

    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Use a nonempty name without control characters")
        return value


class CredentialResponse(BaseModel):
    """Bound the WebAuthn JSON before the maintained verifier parses CBOR/crypto."""

    model_config = ConfigDict(extra="forbid")
    credential: dict[str, object]

    @field_validator("credential")
    @classmethod
    def bounded_credential(cls, value: dict[str, object]) -> dict[str, object]:
        if len(json.dumps(value).encode("utf-8")) > 65536:
            raise ValueError("Passkey response is too large")
        return value


class PasskeyResponse(BaseModel):
    """Only account-visible labels and timestamps, never key material or handles."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None


def relying_party(*, require_secure: bool = True) -> tuple[str, str]:
    """Derive exact trusted origin/RP from configuration, never proxy or Host input."""

    parsed = urlsplit(str(get_settings().app.base_url))
    hostname = parsed.hostname
    if not hostname or (require_secure and parsed.scheme != "https" and hostname != "localhost"):
        raise ApiError(
            409, "passkeys_https_required", "Passkeys require the configured HTTPS address or localhost"
        )
    port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80
    host = f"[{hostname}]" if ":" in hostname else hostname
    authority = host if port in (None, default_port) else f"{host}:{port}"
    return hostname, f"{parsed.scheme}://{authority}"


def guard_request(request: Request, *, require_secure: bool = True) -> tuple[str, str]:
    """Enforce exact browser origin and bounded attempts before each public ceremony."""

    rp_id, origin = relying_party(require_secure=require_secure)
    if request.headers.get("origin") != origin:
        raise ApiError(403, "passkey_origin_invalid", "Use the configured application address for passkeys")
    key = request.client.host if request.client else "unknown"
    if not passkey_limiter.allow(key):
        raise ApiError(429, "passkey_rate_limited", "Try again later")
    return rp_id, origin


def challenge_cookie(purpose: str) -> str:
    """Keep enrollment and login independently bound to their initiating browser."""

    return f"fm_passkey_{purpose}"


async def begin_challenge(
    session: DatabaseSession,
    request: Request,
    response: Response,
    *,
    purpose: str,
    challenge: bytes,
    user: User | None = None,
    name: str | None = None,
) -> None:
    """Replace this browser's prior ceremony and clean expired records atomically."""

    now = datetime.now(UTC)
    old_token = request.cookies.get(challenge_cookie(purpose))
    await session.execute(delete(PasskeyChallenge).where(PasskeyChallenge.expires_at <= now))
    if old_token:
        await session.execute(
            delete(PasskeyChallenge).where(PasskeyChallenge.token_hash == hash_token(old_token))
        )
    token = secrets.token_urlsafe(48)
    session.add(
        PasskeyChallenge(
            token_hash=hash_token(token),
            purpose=purpose,
            challenge=challenge,
            expires_at=now + timedelta(seconds=CEREMONY_SECONDS),
            user_id=user.id if user else None,
            user_version=user.record_version if user else None,
            session_hash=hash_token(request.cookies.get(SESSION_COOKIE, "")) if user else None,
            name=name,
        )
    )
    await session.commit()
    response.set_cookie(
        challenge_cookie(purpose),
        token,
        max_age=CEREMONY_SECONDS,
        httponly=True,
        secure=get_settings().app.secure_cookies,
        samesite="strict",
        path="/api/v1/auth/passkeys",
    )


async def consume_challenge(
    session: DatabaseSession,
    request: Request,
    *,
    purpose: str,
    user: User | None = None,
) -> PasskeyChallenge:
    """Consume even a failed attempt, with a row lock preventing concurrent replay."""

    token = request.cookies.get(challenge_cookie(purpose), "")
    challenge = await session.scalar(
        select(PasskeyChallenge)
        .where(
            PasskeyChallenge.token_hash == hash_token(token),
            PasskeyChallenge.purpose == purpose,
        )
        .with_for_update()
    )
    if challenge is None:
        raise ApiError(401, "passkey_challenge_expired", "Passkey request expired; try again")
    valid = challenge.expires_at > datetime.now(UTC)
    if user:
        valid = valid and challenge.user_id == user.id and challenge.user_version == user.record_version
        valid = valid and challenge.session_hash == hash_token(request.cookies.get(SESSION_COOKIE, ""))
    await session.delete(challenge)
    # Deliberately persist consumption before verification: a rejected signature
    # cannot reuse the challenge, and later transaction rollback cannot resurrect it.
    await session.commit()
    if not valid:
        raise ApiError(401, "passkey_challenge_expired", "Passkey request expired; try again")
    return challenge


async def confirm_password(session: DatabaseSession, user: User, password: str) -> User:
    """Lock the account and require fresh password verification for credential changes."""

    locked = await session.scalar(
        select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True)
    )
    assert locked is not None
    if not verify_password(locked.password_hash, password):
        raise ApiError(401, "current_password_invalid", "Current password is incorrect")
    return locked


@router.get("/availability")
async def availability() -> dict[str, bool]:
    """Expose deployment readiness without revealing whether any credentials exist."""

    try:
        relying_party()
    except ApiError:
        return {"available": False}
    return {"available": True}


@router.get("", response_model=list[PasskeyResponse])
async def list_passkeys(user: Administrator, session: DatabaseSession) -> list[PasskeyResponse]:
    """List the signed-in account's retained friendly labels."""

    keys = await session.scalars(
        select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.created_at)
    )
    return [PasskeyResponse.model_validate(key) for key in keys]


@router.post("/register/options")
async def registration_options(
    payload: Enrollment,
    request: Request,
    response: Response,
    user: Administrator,
    session: DatabaseSession,
) -> dict[str, object]:
    """Authorize registration using CSRF plus fresh password and discoverable UV."""

    rp_id, _ = guard_request(request)
    locked = await confirm_password(session, user, payload.current_password)
    keys = list(await session.scalars(select(Passkey).where(Passkey.user_id == locked.id)))
    if len(keys) >= MAX_PASSKEYS:
        raise ApiError(409, "passkey_limit", "Remove an unused passkey before adding another")
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Filament Manager",
        user_id=locked.id.bytes,
        user_name=locked.username,
        user_display_name=locked.display_name,
        timeout=CEREMONY_SECONDS * 1000,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=key.credential_id) for key in keys if key.rp_id == rp_id
        ],
    )
    await begin_challenge(
        session,
        request,
        response,
        purpose="register",
        challenge=options.challenge,
        user=locked,
        name=payload.name,
    )
    return cast(dict[str, object], json.loads(options_to_json(options)))


@router.post("/register/verify", response_model=PasskeyResponse)
async def registration_verify(
    payload: CredentialResponse,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> PasskeyResponse:
    """Verify origin, challenge, RP, and user verification before saving public data."""

    rp_id, origin = guard_request(request)
    challenge = await consume_challenge(session, request, purpose="register", user=user)
    try:
        verified = verify_registration_response(
            credential=payload.credential,
            expected_challenge=challenge.challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except VERIFICATION_ERRORS as exc:
        raise ApiError(
            401, "passkey_verification_failed", "Passkey could not be verified; try again"
        ) from exc
    locked = await session.scalar(
        select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True)
    )
    if locked is None or locked.record_version != challenge.user_version or not locked.is_active:
        raise ApiError(409, "passkey_account_changed", "Account changed; start passkey setup again")
    if await session.scalar(select(Passkey.id).where(Passkey.credential_id == verified.credential_id)):
        raise ApiError(409, "passkey_exists", "This passkey is already registered")
    count = await session.scalar(select(func.count()).select_from(Passkey).where(Passkey.user_id == user.id))
    if (count or 0) >= MAX_PASSKEYS:
        raise ApiError(409, "passkey_limit", "Remove an unused passkey before adding another")
    if len(verified.credential_id) > 1024 or len(verified.credential_public_key) > 4096:
        raise ApiError(401, "passkey_verification_failed", "Passkey could not be verified; try again")
    key = Passkey(
        user_id=user.id,
        name=challenge.name or "Passkey",
        rp_id=rp_id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        device_type=verified.credential_device_type.value,
        backed_up=verified.credential_backed_up,
        transports=[],
    )
    session.add(key)
    await session.flush()
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="auth.passkey.add",
        object_type="passkey",
        object_id=key.id,
        before=None,
        after={"registered": True},
        correlation_id=request.state.correlation_id,
    )
    result = PasskeyResponse.model_validate(key)
    await session.commit()
    return result


@router.post("/login/options")
async def authentication_options(
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> dict[str, object]:
    """Request discoverable credentials without publishing identifiers or account existence."""

    rp_id, _ = guard_request(request)
    options = generate_authentication_options(
        rp_id=rp_id,
        timeout=CEREMONY_SECONDS * 1000,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    await begin_challenge(session, request, response, purpose="login", challenge=options.challenge)
    return cast(dict[str, object], json.loads(options_to_json(options)))


@router.post("/login/verify", response_model=LoginResponse)
async def authentication_verify(
    payload: CredentialResponse,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> LoginResponse:
    """Verify assertion and counter under a credential lock, then rotate browser sessions."""

    rp_id, origin = guard_request(request)
    challenge = await consume_challenge(session, request, purpose="login")
    try:
        credential_id = base64url_to_bytes(str(payload.credential.get("id", "")))
        if not 1 <= len(credential_id) <= 1024:
            raise ValueError("Invalid credential length")
        owner_id = await session.scalar(
            select(Passkey.user_id).where(
                Passkey.credential_id == credential_id,
                Passkey.rp_id == rp_id,
            )
        )
        if owner_id is None:
            raise ValueError("Unknown credential")
        # All credential mutations lock account before credential, avoiding a
        # removal/sign-in deadlock. Re-read the key after acquiring those locks.
        user = await session.scalar(select(User).where(User.id == owner_id).with_for_update())
        key = await session.scalar(
            select(Passkey)
            .where(
                Passkey.credential_id == credential_id,
                Passkey.rp_id == rp_id,
                Passkey.user_id == owner_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(UTC)
        if (
            key is None
            or user is None
            or not user.is_active
            or (user.locked_until is not None and user.locked_until > now)
        ):
            raise ValueError("Account unavailable")
        raw_response = payload.credential.get("response")
        if not isinstance(raw_response, dict):
            raise ValueError("Missing assertion")
        # Discoverable authentication must identify the credential's account;
        # accepting a different/missing user handle breaks username-free login.
        if base64url_to_bytes(str(raw_response.get("userHandle", ""))) != user.id.bytes:
            raise ValueError("Invalid account handle")
        verified = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=challenge.challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=key.public_key,
            credential_current_sign_count=key.sign_count,
            require_user_verification=True,
        )
    except VERIFICATION_ERRORS as exc:
        raise ApiError(
            401, "passkey_verification_failed", "Passkey could not be verified; try again"
        ) from exc
    key.sign_count = verified.new_sign_count
    key.backed_up = verified.credential_backed_up
    key.device_type = verified.credential_device_type.value
    key.last_used_at = now
    return await issue_browser_session(
        session, user, request, response, method="passkey", settings=get_settings()
    )


@router.post("/{passkey_id}/remove", status_code=204)
async def remove_passkey(
    passkey_id: UUID,
    payload: PasswordConfirmation,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> Response:
    """Require fresh password, remove only this account's credential, and revoke other sessions."""

    guard_request(request, require_secure=False)
    await confirm_password(session, user, payload.current_password)
    key = await session.scalar(
        select(Passkey)
        .where(
            Passkey.id == passkey_id,
            Passkey.user_id == user.id,
        )
        .with_for_update()
    )
    if key is None:
        raise ApiError(404, "passkey_not_found", "Passkey not found")
    await session.delete(key)
    await session.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.token_hash != hash_token(request.cookies.get(SESSION_COOKIE, "")),
        )
    )
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="auth.passkey.remove",
        object_type="passkey",
        object_id=passkey_id,
        before=None,
        after={"removed": True, "other_sessions_revoked": True},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return Response(status_code=204)
