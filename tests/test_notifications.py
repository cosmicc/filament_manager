"""Persistent operator-notification classification tests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.models.auth import User
from filament_manager.models.base import Base
from filament_manager.models.enums import CuraDeploymentStatus, NotificationSeverity, UserRole
from filament_manager.models.operations import Notification
from filament_manager.models.workstations import CuraDeployment, WorkstationAgent
from filament_manager.security import hash_password
from filament_manager.services.notifications import (
    _cura_failure_notification,
    evaluate_operator_notifications,
    upsert_notification,
)


def test_cura_failure_notifications_exclude_backup_request_history() -> None:
    """A failed named backup stays in Recovery points without posing as a sync alert."""

    agent = SimpleNamespace(id=uuid4(), display_name="Workshop Cura")
    deployment = SimpleNamespace(operation="recovery_capture")

    assert _cura_failure_notification(deployment, agent) is None


def test_cura_failure_notifications_are_operation_scoped() -> None:
    """Repeated deployment rows converge to one alert per workstation operation."""

    agent = SimpleNamespace(id=uuid4(), display_name="Workshop Cura")
    deployment = SimpleNamespace(operation="material_library")

    first = _cura_failure_notification(deployment, agent)
    second = _cura_failure_notification(deployment, agent)

    assert first == second
    assert first is not None
    assert first[0] == f"cura-deployment:{agent.id}:material_library:failed"
    assert first[1] == "Cura synchronization failed on Workshop Cura"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cura_notifications_use_only_newest_operation_state() -> None:
    """New success resolves old failures and backup requests never become sync alerts."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        now = datetime.now(UTC)
        async with factory() as session:
            administrator = User(
                username="notification-admin",
                normalized_username="notification-admin",
                display_name="Notification Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            session.add(administrator)
            await session.flush()
            agent = WorkstationAgent(
                agent_code="WS-NOTIFY",
                display_name="Workshop Cura",
                hostname="workshop",
                platform="arch_linux",
                architecture="x86_64",
                agent_version="0.5.0",
                token_hash="a" * 64,
                created_by=administrator.id,
            )
            session.add(agent)
            await session.flush()

            def deployment(
                *,
                operation: str | None,
                status: CuraDeploymentStatus,
                created_at: datetime,
                suffix: str,
            ) -> CuraDeployment:
                payload = {"schema_version": 3} if operation is None else {"operation": operation}
                return CuraDeployment(
                    agent_id=agent.id,
                    material_profile_id=None,
                    requested_by=administrator.id,
                    status=status,
                    payload=payload,
                    profile_checksum=suffix * 64,
                    idempotency_key=f"notification-test:{suffix}",
                    attempts=1,
                    next_attempt_at=created_at,
                    created_at=created_at,
                    updated_at=created_at,
                    completed_at=created_at,
                    last_error_class="RuntimeError" if status == CuraDeploymentStatus.FAILED else None,
                    last_error_message=(
                        "A sanitized workstation operation failed."
                        if status == CuraDeploymentStatus.FAILED
                        else None
                    ),
                )

            old_library_failure = deployment(
                operation=None,
                status=CuraDeploymentStatus.FAILED,
                created_at=now - timedelta(minutes=4),
                suffix="b",
            )
            current_library_success = deployment(
                operation=None,
                status=CuraDeploymentStatus.SUCCEEDED,
                created_at=now - timedelta(minutes=3),
                suffix="c",
            )
            failed_backup = deployment(
                operation="recovery_capture",
                status=CuraDeploymentStatus.FAILED,
                created_at=now - timedelta(minutes=2),
                suffix="d",
            )
            failed_nozzle = deployment(
                operation="nozzle_update",
                status=CuraDeploymentStatus.FAILED,
                created_at=now - timedelta(minutes=1),
                suffix="e",
            )
            session.add_all([old_library_failure, current_library_success, failed_backup, failed_nozzle])
            await session.flush()
            legacy = await upsert_notification(
                session,
                deduplication_key=f"cura-deployment:{old_library_failure.id}:failed",
                category="cura_deployment_failed",
                severity=NotificationSeverity.ERROR,
                title="Cura synchronization failed on Workshop Cura",
                message="Legacy per-record notification.",
                action_path="/workstations",
                object_type="cura_deployment",
                object_id=old_library_failure.id,
            )
            await session.commit()
            legacy_id = legacy.id
            failed_nozzle_id = failed_nozzle.id

        async with factory() as session:
            await evaluate_operator_notifications(session)
            active = list(
                await session.scalars(
                    select(Notification).where(
                        Notification.category == "cura_deployment_failed",
                        Notification.active.is_(True),
                    )
                )
            )
            assert len(active) == 1
            assert active[0].deduplication_key == (f"cura-deployment:{agent.id}:nozzle_update:failed")
            assert active[0].object_id == failed_nozzle_id
            assert active[0].title == "Cura nozzle synchronization failed on Workshop Cura"
            resolved_legacy = await session.get(Notification, legacy_id)
            assert resolved_legacy is not None
            assert resolved_legacy.active is False

        await engine.dispose()
