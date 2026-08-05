"""Local account, session, and administrator user-management routes."""

import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from filament_manager.config import get_settings
from filament_manager.models.auth import User, UserSession
from filament_manager.security import (
    create_session_tokens,
    hash_password,
    hash_token,
    normalize_username,
    verify_password,
)
from filament_manager.services.events import add_audit_event

from ..dependencies import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Administrator,
    CurrentUser,
    DatabaseSession,
)
from ..errors import ApiError
from ..schemas import LoginRequest, LoginResponse, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRateLimiter:
    """Bound login attempts per process and client address."""

    def __init__(self, attempts: int = 12, window_seconds: int = 300) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = self._events[key]
        while events and events[0] < now - self.window_seconds:
            events.popleft()
        if len(events) >= self.attempts:
            return False
        events.append(now)
        return True


login_limiter = LoginRateLimiter()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> LoginResponse:
    """Verify local credentials and issue revocable HttpOnly session cookies."""

    if not login_limiter.allow(_client_key(request)):
        raise ApiError(status.HTTP_429_TOO_MANY_REQUESTS, "login_rate_limited", "Try again later")

    settings = get_settings()
    normalized = normalize_username(payload.username)
    result = await session.execute(select(User).where(User.normalized_username == normalized))
    user = result.scalar_one_or_none()
    now = datetime.now(UTC)
    valid = bool(
        user
        and user.is_active
        and (user.locked_until is None or user.locked_until <= now)
        and verify_password(user.password_hash, payload.password)
    )

    if not valid:
        if user is not None:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.security.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.security.lockout_minutes)
                user.failed_login_attempts = 0
            await session.commit()
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Invalid credentials")

    assert user is not None
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    tokens = create_session_tokens(settings.security)
    browser_session = UserSession(
        user_id=user.id,
        token_hash=hash_token(tokens.session_token),
        csrf_hash=hash_token(tokens.csrf_token),
        created_at=tokens.created_at,
        last_seen_at=tokens.created_at,
        expires_at=tokens.expires_at,
        idle_expires_at=tokens.idle_expires_at,
        user_agent=request.headers.get("user-agent", "")[:256] or None,
    )
    session.add(browser_session)
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="auth.login",
        object_type="user",
        object_id=user.id,
        before=None,
        after={"username": user.username, "role": user.role.value},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()

    max_age = settings.security.session_lifetime_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        tokens.session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.app.secure_cookies,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.app.secure_cookies,
        samesite="strict",
        path="/",
    )
    return LoginResponse(user=UserResponse.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    """Revoke the current session and clear browser cookies."""

    token = request.cookies.get(SESSION_COOKIE)
    if token:
        result = await session.execute(select(UserSession).where(UserSession.token_hash == hash_token(token)))
        browser_session = result.scalar_one_or_none()
        if browser_session:
            await session.delete(browser_session)
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action="auth.logout",
        object_type="user",
        object_id=user.id,
        before=None,
        after=None,
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    """Return the signed-in account and role."""

    return UserResponse.model_validate(user)


@router.get("/users", response_model=list[UserResponse])
async def list_users(_: Administrator, session: DatabaseSession) -> list[UserResponse]:
    """List local accounts for administrator management."""

    result = await session.execute(select(User).order_by(User.username))
    return [UserResponse.model_validate(user) for user in result.scalars()]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> UserResponse:
    """Create a local role account with an Argon2id password hash."""

    normalized = normalize_username(payload.username)
    existing = await session.scalar(select(User.id).where(User.normalized_username == normalized))
    if existing:
        raise ApiError(status.HTTP_409_CONFLICT, "username_exists", "Username already exists")
    user = User(
        username=payload.username.strip(),
        normalized_username=normalized,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.flush()
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="user.create",
        object_type="user",
        object_id=user.id,
        before=None,
        after={"username": user.username, "role": user.role.value},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return UserResponse.model_validate(user)
