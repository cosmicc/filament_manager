"""Administrator-only Google setup; never expose stored credential material."""

import json
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from filament_manager.api.dependencies import SESSION_COOKIE, Administrator, DatabaseSession
from filament_manager.api.errors import ApiError
from filament_manager.clients.google_sheets import GoogleSheetsError
from filament_manager.config import get_settings
from filament_manager.models.google import GoogleConnection
from filament_manager.security import hash_token
from filament_manager.services import google_connection as google
from filament_manager.services.credentials import CredentialError, writable_cipher
from filament_manager.services.events import add_audit_event

router = APIRouter(prefix="/settings/google", tags=["settings"])
DbSession = DatabaseSession


class GoogleCompletion(BaseModel):
    """Bounded short-lived proof; validation errors must never echo its values."""

    code: str = Field(min_length=1, max_length=8192)
    state: str = Field(min_length=32, max_length=128)


class GoogleSetup(BaseModel):
    """An explicitly supplied Google Web OAuth download, never logged or exported."""

    credentials_json: str = Field(min_length=2, max_length=32768)


@router.post("/setup")
async def setup(
    payload: GoogleSetup, request: Request, user: Administrator, session: DbSession
) -> dict[str, bool]:
    """Save validated app-owned credentials, invalidating any prior consent attempt."""
    settings = get_settings()
    if settings.google.enabled:
        raise ApiError(409, "google_legacy", "Disable legacy service-account publishing before guided setup.")
    try:
        document = json.loads(payload.credentials_json)
        web = document.get("web") if isinstance(document, dict) else None
        if not isinstance(web, dict):
            raise ValueError
        client_id, secret = web.get("client_id"), web.get("client_secret")
        redirects = web.get("redirect_uris")
        if not isinstance(client_id, str) or not re.fullmatch(
            r"[A-Za-z0-9._-]{1,450}\.apps\.googleusercontent\.com", client_id
        ):
            raise ValueError
        if (
            not isinstance(secret, str)
            or not 1 <= len(secret) <= 4096
            or any(ord(char) < 33 for char in secret)
        ):
            raise ValueError
        if not isinstance(redirects, list) or google.redirect_uri(settings) not in redirects:
            raise ApiError(
                422,
                "google_redirect",
                "Add the displayed redirect URL to this Web OAuth client and download its JSON again.",
            )
    except (ValueError, TypeError):
        raise ApiError(
            422, "google_credentials", "Upload a valid Google OAuth Web application credentials JSON file."
        ) from None
    record = await google.connection(session, lock=True)
    try:
        cipher = await writable_cipher(session, settings)
    except CredentialError as exc:
        raise ApiError(409, "credential_storage", str(exc)) from None
    record.oauth_client_id = client_id
    record.oauth_client_secret = cipher.encrypt(secret.encode()).decode()
    record.refresh_token = record.verifier = record.state_hash = None
    record.session_hash = "setup_changed"
    record.connected_at = record.state_expires_at = record.sync_requested_at = None
    record.last_error = None
    record.next_attempt_at = None
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="google.setup",
        object_type="google",
        object_id=None,
        before=None,
        after={"credentials_configured": True},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"saved": True}


@router.get("")
async def status(user: Administrator, session: DbSession) -> dict[str, object]:
    """Return safe setup and publication state, without making Google requests."""
    settings = get_settings()
    record = await session.get(GoogleConnection, 1)
    spreadsheet = (record.spreadsheet_id if record else None) or settings.google.spreadsheet_id
    return {
        "ready": google.oauth_ready(settings, record),
        "credentials_saved": bool(record and record.oauth_client_secret),
        "legacy": settings.google.enabled,
        "connected": bool(record and record.refresh_token) or settings.google.enabled,
        "redirect_uri": google.redirect_uri(settings),
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet}/edit"
        if spreadsheet
        else None,
        "last_synced_at": record.last_synced_at.isoformat() if record and record.last_synced_at else None,
        "last_error": record.last_error if record else None,
        "next_attempt_at": record.next_attempt_at.isoformat() if record and record.next_attempt_at else None,
        "sync_requested": bool(record and record.sync_requested_at),
        "interval_seconds": settings.google.publish_interval_seconds,
    }


@router.post("/connect")
async def connect(request: Request, user: Administrator, session: DbSession) -> dict[str, str]:
    """Start explicit OAuth consent, guarded by ordinary application CSRF."""
    try:
        url = await google.begin_authorization(session, hash_token(request.cookies[SESSION_COOKIE]))
    except GoogleSheetsError as exc:
        raise ApiError(400, "google_setup", str(exc)) from None
    return {"authorization_url": url}


@router.post("/complete")
async def complete(
    payload: GoogleCompletion,
    request: Request,
    user: Administrator,
    session: DbSession,
) -> dict[str, bool]:
    """Complete from a first-party page, preserving SameSite=Strict cookies."""
    try:
        await google.complete_authorization(
            session, hash_token(request.cookies[SESSION_COOKIE]), payload.state, payload.code
        )
    except GoogleSheetsError as exc:
        raise ApiError(400, "google_authorization", str(exc)) from None
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="google.connected",
        object_type="google",
        object_id=None,
        before=None,
        after=None,
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"connected": True}


@router.post("/sync")
async def sync(request: Request, user: Administrator, session: DbSession) -> dict[str, bool]:
    """Persist a coalesced force-publication request for the worker."""
    record = await google.connection(session, lock=True)
    if not record.refresh_token and not get_settings().google.enabled:
        raise ApiError(409, "google_disconnected", "Connect Google before synchronizing.")
    record.sync_requested_at = datetime.now(UTC)
    record.next_attempt_at = None
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="google.sync_requested",
        object_type="google",
        object_id=None,
        before=None,
        after=None,
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"queued": True}


@router.post("/disconnect")
async def disconnect(request: Request, user: Administrator, session: DbSession) -> dict[str, bool]:
    """Forget local access; retain the workbook and its stable publication identity."""
    if get_settings().google.enabled:
        raise ApiError(
            409, "google_legacy", "Disable the service-account publisher in deployment settings first."
        )
    record = await google.connection(session, lock=True)
    record.refresh_token = record.verifier = record.state_hash = None
    # A tombstone prevents an already exchanging callback from reconnecting.
    record.session_hash = "disconnected"
    record.state_expires_at = record.connected_at = record.sync_requested_at = None
    record.last_error = None
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="google.disconnected",
        object_type="google",
        object_id=None,
        before=None,
        after=None,
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return {"connected": False}
