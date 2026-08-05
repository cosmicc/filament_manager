"""Authenticated-user, role, CSRF, and request-context dependencies."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from filament_manager.database import session_dependency
from filament_manager.models.auth import User, UserSession
from filament_manager.models.enums import UserRole
from filament_manager.models.workstations import WorkstationAgent
from filament_manager.security import hash_token

from .errors import ApiError

SESSION_COOKIE = "fm_session"
CSRF_COOKIE = "fm_csrf"

DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


async def current_user(
    request: Request,
    session: DatabaseSession,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> User:
    """Resolve an active, unexpired local session and enforce CSRF on writes."""

    if not session_token:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "authentication_required", "Sign in required")

    token_hash = hash_token(session_token)
    result = await session.execute(
        select(UserSession).where(UserSession.token_hash == token_hash).options(joinedload(UserSession.user))
    )
    browser_session = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if browser_session is None or browser_session.expires_at <= now or browser_session.idle_expires_at <= now:
        if browser_session is not None:
            await session.execute(delete(UserSession).where(UserSession.id == browser_session.id))
            await session.commit()
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "session_expired", "Session expired")
    if not browser_session.user.is_active:
        raise ApiError(status.HTTP_403_FORBIDDEN, "account_disabled", "Account is disabled")

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not csrf_cookie or not csrf_header or not secrets_equal(csrf_cookie, csrf_header):
            raise ApiError(status.HTTP_403_FORBIDDEN, "csrf_failed", "Request verification failed")
        if not secrets_equal(hash_token(csrf_header), browser_session.csrf_hash):
            raise ApiError(status.HTTP_403_FORBIDDEN, "csrf_failed", "Request verification failed")

    return browser_session.user


def secrets_equal(left: str, right: str) -> bool:
    """Compare security-sensitive strings in constant time."""

    import secrets

    return secrets.compare_digest(left, right)


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*allowed: UserRole) -> Callable[[User], Awaitable[User]]:
    """Create a dependency that permits only the supplied roles."""

    async def role_dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise ApiError(status.HTTP_403_FORBIDDEN, "forbidden", "Insufficient permission")
        return user

    return role_dependency


Administrator = Annotated[User, Depends(require_roles(UserRole.ADMINISTRATOR))]
Operator = Annotated[User, Depends(require_roles(UserRole.ADMINISTRATOR, UserRole.OPERATOR))]
Viewer = Annotated[
    User,
    Depends(require_roles(UserRole.ADMINISTRATOR, UserRole.OPERATOR, UserRole.VIEWER)),
]


async def current_workstation_agent(
    session: DatabaseSession,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> WorkstationAgent:
    """Resolve an enabled workstation from its scoped bearer credential."""

    scheme, separator, token = (authorization or "").partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.startswith("fm_agent_"):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "agent_authentication_required", "Agent credential required"
        )
    agent = await session.scalar(
        select(WorkstationAgent).where(WorkstationAgent.token_hash == hash_token(token))
    )
    if agent is None or not agent.enabled:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "agent_credential_invalid", "Agent credential invalid")
    return agent


CurrentWorkstationAgent = Annotated[WorkstationAgent, Depends(current_workstation_agent)]
