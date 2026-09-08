"""Session-bound Google OAuth and encrypted offline credentials.

Only fixed Google origins receive credentials. Provider response bodies and
exceptions never cross this boundary, including into worker logs.
"""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.clients.google_sheets import GoogleSheetsError
from filament_manager.config import Settings, get_settings
from filament_manager.models.auth import UserSession
from filament_manager.models.google import GoogleConnection
from filament_manager.services.credentials import CredentialError, credential_cipher, decrypt_credential

GOOGLE_LOCK = 0x464D474F4F47
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - fixed public endpoint, not a token


def redirect_uri(settings: Settings) -> str:
    """Use the configured public origin, never an untrusted Host header."""
    return str(settings.app.base_url).rstrip("/") + "/google/callback"


def encryption(settings: Settings) -> Fernet:
    """Validate the deployment key without exposing it in validation errors."""
    try:
        return credential_cipher(settings)
    except CredentialError:
        raise GoogleSheetsError(
            "Complete guided Google setup or restore the private encryption key."
        ) from None


def oauth_ready(settings: Settings, record: GoogleConnection | None = None) -> bool:
    """Indicate readiness without returning any credential values."""
    origin = urlsplit(redirect_uri(settings))
    if origin.scheme != "https" and origin.hostname not in ("localhost", "127.0.0.1", "::1"):
        return False
    try:
        encryption(settings)
    except GoogleSheetsError:
        return False
    return bool(
        (record and record.oauth_client_id and record.oauth_client_secret)
        or (settings.google.oauth_client_id and settings.google.oauth_client_secret)
    )


def client_credentials(settings: Settings, record: GoogleConnection | None) -> tuple[str, str]:
    """Prefer explicitly saved UI credentials; never return these to the browser."""
    if record and record.oauth_client_id and record.oauth_client_secret:
        try:
            return record.oauth_client_id, decrypt_credential(settings, record.oauth_client_secret)
        except CredentialError as exc:
            raise GoogleSheetsError(str(exc)) from None
    if settings.google.oauth_client_id and settings.google.oauth_client_secret:
        return settings.google.oauth_client_id, settings.google.oauth_client_secret.get_secret_value()
    raise GoogleSheetsError("Complete guided Google setup before connecting.")


async def connection(session: AsyncSession, *, lock: bool = False) -> GoogleConnection:
    """Create one durable identity and serialize authorization/publication work."""
    if lock:
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": GOOGLE_LOCK})
    await session.execute(
        insert(GoogleConnection)
        .values(id=1, publication_key=str(uuid4()))
        .on_conflict_do_nothing(index_elements=["id"])
    )
    result = await session.get(GoogleConnection, 1, populate_existing=True)
    assert result is not None
    return result


async def begin_authorization(session: AsyncSession, session_hash: str) -> str:
    """Persist one ten-minute PKCE attempt bound to the current browser session."""
    settings = get_settings()
    record = await connection(session, lock=True)
    if not oauth_ready(settings, record) or settings.google.enabled:
        raise GoogleSheetsError("Complete Google OAuth deployment setup before connecting.")
    client_id, _ = client_credentials(settings, record)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    record.state_hash = hashlib.sha256(state.encode()).hexdigest()
    record.session_hash = session_hash
    record.verifier = encryption(settings).encrypt(verifier.encode()).decode()
    record.state_expires_at = datetime.now(UTC) + timedelta(minutes=10)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    await session.commit()
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri(settings),
            "response_type": "code",
            "scope": DRIVE_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


async def token_request(fields: dict[str, str], record: GoogleConnection | None = None) -> dict[str, Any]:
    """Exchange/refresh credentials with bounded time and sanitized failures."""
    settings = get_settings()
    client_id, secret = client_credentials(settings, record)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    **fields,
                    "client_id": client_id,
                    "client_secret": secret,
                },
            )
        if response.status_code != 200 or len(response.content) > 65536:
            raise ValueError
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError
        return body
    except (httpx.HTTPError, ValueError):
        raise GoogleSheetsError("Google authorization failed. Check setup or reconnect Google.") from None


async def complete_authorization(
    session: AsyncSession,
    session_hash: str,
    state: str,
    code: str,
) -> None:
    """Consume state once; a revoked/expired app session is rejected upstream."""
    settings = get_settings()
    record = await connection(session, lock=True)
    if (
        not record.state_hash
        or not record.session_hash
        or not record.verifier
        or not record.state_expires_at
        or record.state_expires_at <= datetime.now(UTC)
        or not secrets.compare_digest(record.session_hash, session_hash)
        or not secrets.compare_digest(record.state_hash, hashlib.sha256(state.encode()).hexdigest())
    ):
        raise GoogleSheetsError("Google sign-in expired or belongs to another session. Connect again.")
    try:
        verifier = encryption(settings).decrypt(record.verifier.encode()).decode()
    except (InvalidToken, ValueError):
        raise GoogleSheetsError("Google sign-in could not be verified. Connect again.") from None
    completion_id = secrets.token_hex(32)
    record.state_hash = record.verifier = None
    record.session_hash = completion_id
    record.state_expires_at = None
    # Commit consumption before the external exchange; retries cannot replay the code.
    await session.commit()
    body = await token_request(
        {
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri(settings),
            "grant_type": "authorization_code",
        },
        record,
    )
    token = body.get("refresh_token")
    if not isinstance(token, str) or not 1 <= len(token) <= 8192:
        raise GoogleSheetsError("Google did not grant offline access. Connect again and allow access.")
    if DRIVE_SCOPE not in str(body.get("scope", "")).split():
        raise GoogleSheetsError("Google file access was not granted. Connect again and allow access.")
    record = await connection(session, lock=True)
    # A newer connect/disconnect operation invalidates an in-flight exchange.
    if record.state_hash or record.session_hash != completion_id:
        raise GoogleSheetsError("Google setup changed. Connect again.")
    active_session = await session.scalar(
        select(UserSession.id).where(
            UserSession.token_hash == session_hash,
            UserSession.expires_at > datetime.now(UTC),
            UserSession.idle_expires_at > datetime.now(UTC),
        )
    )
    if active_session is None:
        raise GoogleSheetsError("Your app session expired. Sign in and connect Google again.")
    if record.mode != "oauth":
        record.spreadsheet_id = None
        record.publication_key = str(uuid4())
    record.mode = "oauth"
    record.refresh_token = encryption(settings).encrypt(token.encode()).decode()
    record.session_hash = None
    record.connected_at = datetime.now(UTC)
    record.last_error = None
    record.failures = 0
    record.next_attempt_at = None
    record.last_fingerprint = None
    record.sync_requested_at = datetime.now(UTC)
    await session.commit()


async def access_token(record: GoogleConnection) -> str:
    """Decrypt only at the outbound boundary; access tokens are never persisted."""
    try:
        refresh = encryption(get_settings()).decrypt((record.refresh_token or "").encode()).decode()
    except (InvalidToken, ValueError):
        raise GoogleSheetsError(
            "Google credentials cannot be decrypted. Restore the key or reconnect."
        ) from None
    body = await token_request({"refresh_token": refresh, "grant_type": "refresh_token"}, record)
    token = body.get("access_token")
    if not isinstance(token, str) or not 1 <= len(token) <= 8192:
        raise GoogleSheetsError("Google access expired. Reconnect Google.")
    return token
