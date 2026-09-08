"""Administrator-only Google setup; never expose stored credential material."""

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
from filament_manager.services.events import add_audit_event

router = APIRouter(prefix="/settings/google", tags=["settings"])
DbSession = DatabaseSession


class GoogleCompletion(BaseModel):
    """Bounded short-lived proof; validation errors must never echo its values."""

    code: str = Field(min_length=1, max_length=8192)
    state: str = Field(min_length=32, max_length=128)


@router.get("")
async def status(user: Administrator, session: DbSession) -> dict[str, object]:
    """Return safe setup and publication state, without making Google requests."""
    settings = get_settings()
    record = await session.get(GoogleConnection, 1)
    spreadsheet = (record.spreadsheet_id if record else None) or settings.google.spreadsheet_id
    return {
        "ready": google.oauth_ready(settings),
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
