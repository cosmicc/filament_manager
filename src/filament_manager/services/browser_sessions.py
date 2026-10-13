"""Issue the same revocable browser session after password or passkey verification."""

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.api.dependencies import CSRF_COOKIE, SESSION_COOKIE
from filament_manager.api.schemas import LoginResponse, UserResponse
from filament_manager.config import Settings
from filament_manager.models.auth import User, UserSession
from filament_manager.security import create_session_tokens, hash_token
from filament_manager.services.events import add_audit_event


async def issue_browser_session(
    session: AsyncSession,
    user: User,
    request: Request,
    response: Response,
    *,
    method: str,
    settings: Settings,
) -> LoginResponse:
    """Commit authentication and rotate strict cookies without extending old sessions."""

    tokens = create_session_tokens(settings.security)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = tokens.created_at
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(tokens.session_token),
            csrf_hash=hash_token(tokens.csrf_token),
            created_at=tokens.created_at,
            last_seen_at=tokens.created_at,
            expires_at=tokens.expires_at,
            idle_expires_at=tokens.idle_expires_at,
            user_agent=request.headers.get("user-agent", "")[:256] or None,
        )
    )
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="auth.login",
        object_type="user",
        object_id=user.id,
        before=None,
        after={"username": user.username, "role": user.role.value, "method": method},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    for cookie, value, httponly in (
        (SESSION_COOKIE, tokens.session_token, True),
        (CSRF_COOKIE, tokens.csrf_token, False),
    ):
        response.set_cookie(
            cookie,
            value,
            max_age=settings.security.session_lifetime_hours * 3600,
            httponly=httponly,
            secure=settings.app.secure_cookies,
            samesite="strict",
            path="/",
        )
    return LoginResponse(user=UserResponse.model_validate(user))
