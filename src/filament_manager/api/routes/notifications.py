"""Persistent operator notification center routes."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import and_, select

from filament_manager.models.operations import Notification, UserNotificationState

from ..dependencies import CurrentUser, DatabaseSession, Viewer
from ..errors import ApiError
from ..schemas import NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    user: Viewer,
    session: DatabaseSession,
    active_only: bool = False,
    unread_only: bool = False,
    limit: int = 100,
) -> list[NotificationResponse]:
    """Return newest operator events with the current user's read state."""

    query = (
        select(Notification, UserNotificationState.read_at)
        .outerjoin(
            UserNotificationState,
            and_(
                UserNotificationState.notification_id == Notification.id,
                UserNotificationState.user_id == user.id,
            ),
        )
        .order_by(Notification.active.desc(), Notification.last_seen_at.desc())
        .limit(min(max(limit, 1), 250))
    )
    if active_only:
        query = query.where(Notification.active.is_(True))
    if unread_only:
        query = query.where(UserNotificationState.read_at.is_(None))
    rows = await session.execute(query)
    return [
        NotificationResponse(
            id=notification.id,
            category=notification.category,
            severity=notification.severity,
            title=notification.title,
            message=notification.message,
            action_path=notification.action_path,
            object_type=notification.object_type,
            object_id=notification.object_id,
            active=notification.active,
            occurrence_count=notification.occurrence_count,
            created_at=notification.created_at,
            last_seen_at=notification.last_seen_at,
            resolved_at=notification.resolved_at,
            read=read_at is not None,
        )
        for notification, read_at in rows
    ]


@router.post("/actions/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(user: CurrentUser, session: DatabaseSession) -> None:
    """Mark every currently visible event read for the current account."""

    now = datetime.now(UTC)
    notification_ids = list(await session.scalars(select(Notification.id)))
    existing = {
        state.notification_id: state
        for state in await session.scalars(
            select(UserNotificationState).where(UserNotificationState.user_id == user.id)
        )
    }
    for notification_id in notification_ids:
        state = existing.get(notification_id)
        if state is None:
            session.add(UserNotificationState(user_id=user.id, notification_id=notification_id, read_at=now))
        else:
            state.read_at = now
    await session.commit()


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> None:
    """Mark one shared notification read only for the current account."""

    if await session.get(Notification, notification_id) is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_notification", "Notification not found")
    state = await session.get(UserNotificationState, {"user_id": user.id, "notification_id": notification_id})
    if state is None:
        session.add(
            UserNotificationState(
                user_id=user.id,
                notification_id=notification_id,
                read_at=datetime.now(UTC),
            )
        )
    else:
        state.read_at = datetime.now(UTC)
    await session.commit()
