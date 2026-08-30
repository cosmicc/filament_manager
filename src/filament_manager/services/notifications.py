"""Persistent deduplicated operator notifications and plate due-state evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.models.enums import (
    CuraDeploymentStatus,
    JobStatus,
    NotificationSeverity,
    PlateMaintenanceType,
    PrintJobStatus,
    SpoolStatus,
)
from filament_manager.models.inventory import BuildPlate, BuildPlateSurface, Printer, Spool
from filament_manager.models.operations import (
    BuildPlateMaintenanceEvent,
    Notification,
    OutboxJob,
    UserNotificationState,
)
from filament_manager.models.printing import PrintJob
from filament_manager.models.workstations import CuraDeployment, WorkstationAgent


async def upsert_notification(
    session: AsyncSession,
    *,
    deduplication_key: str,
    category: str,
    severity: NotificationSeverity,
    title: str,
    message: str,
    action_path: str | None,
    object_type: str | None,
    object_id: UUID | None,
) -> Notification:
    """Create or reactivate one bounded condition without periodic duplicates."""

    now = datetime.now(UTC)
    notification = await session.scalar(
        select(Notification).where(Notification.deduplication_key == deduplication_key)
    )
    if notification is None:
        notification = Notification(
            deduplication_key=deduplication_key[:255],
            category=category[:64],
            severity=severity,
            title=title[:160],
            message=message[:500],
            action_path=action_path[:255] if action_path else None,
            object_type=object_type[:64] if object_type else None,
            object_id=object_id,
            active=True,
            occurrence_count=1,
            created_at=now,
            last_seen_at=now,
        )
        session.add(notification)
    else:
        if not notification.active:
            notification.occurrence_count += 1
            await session.execute(
                delete(UserNotificationState).where(UserNotificationState.notification_id == notification.id)
            )
        notification.category = category[:64]
        notification.severity = severity
        notification.title = title[:160]
        notification.message = message[:500]
        notification.action_path = action_path[:255] if action_path else None
        notification.object_type = object_type[:64] if object_type else None
        notification.object_id = object_id
        notification.active = True
        notification.last_seen_at = now
        notification.resolved_at = None
    return notification


async def _resolve_missing_category(session: AsyncSession, *, category: str, active_keys: set[str]) -> None:
    now = datetime.now(UTC)
    notifications = await session.scalars(
        select(Notification).where(Notification.category == category, Notification.active.is_(True))
    )
    for notification in notifications:
        if notification.deduplication_key not in active_keys:
            notification.active = False
            notification.resolved_at = now


def _cura_failure_notification(
    deployment: CuraDeployment,
    agent: WorkstationAgent,
) -> tuple[str, str, str] | None:
    """Return one operation-scoped alert, excluding recovery-request history.

    Named recovery captures already retain their terminal status and sanitized
    error on the Recovery points surface. Treating each failed request as a
    material synchronization condition creates duplicate, permanently active
    alerts even when the current Cura library and recovery snapshot are healthy.
    """

    operation = deployment.operation
    if operation == "recovery_capture":
        return None
    if operation == "nozzle_update":
        title = f"Cura nozzle synchronization failed on {agent.display_name}"
        message = "Open Cura Workstations to review the sanitized failure and retry."
    else:
        title = f"Cura synchronization failed on {agent.display_name}"
        message = "Open Cura Workstations to review the sanitized failure and retry."
    return (
        f"cura-deployment:{agent.id}:{operation}:failed",
        title,
        message,
    )


async def build_plate_maintenance_status(session: AsyncSession, plate: BuildPlate) -> dict[str, object]:
    """Calculate configured day/print due state from immutable print and event history."""

    now = datetime.now(UTC)
    last_cleaned = await session.scalar(
        select(func.max(BuildPlateMaintenanceEvent.occurred_at)).where(
            BuildPlateMaintenanceEvent.build_plate_id == plate.id,
            BuildPlateMaintenanceEvent.maintenance_type == PlateMaintenanceType.CLEANED,
        )
    )
    cleaning_origin = last_cleaned or plate.created_at
    cleaning_prints = (
        await session.scalar(
            select(func.count(PrintJob.id)).where(
                PrintJob.build_plate_id == plate.id,
                PrintJob.status == PrintJobStatus.COMPLETED,
                PrintJob.ended_at >= cleaning_origin,
            )
        )
        or 0
    )
    cleaning_due_at = cleaning_origin + timedelta(days=plate.cleaning_due_after_days)
    surface_statuses: list[dict[str, object]] = []
    surfaces = list(
        await session.scalars(
            select(BuildPlateSurface)
            .where(BuildPlateSurface.build_plate_id == plate.id)
            .order_by(BuildPlateSurface.side)
        )
    )
    for surface in surfaces:
        last_mesh = await session.scalar(
            select(func.max(BuildPlateMaintenanceEvent.occurred_at)).where(
                BuildPlateMaintenanceEvent.build_plate_surface_id == surface.id,
                BuildPlateMaintenanceEvent.maintenance_type == PlateMaintenanceType.MESH_CALIBRATED,
            )
        )
        mesh_origin = last_mesh or surface.created_at
        print_count = (
            await session.scalar(
                select(func.count(PrintJob.id)).where(
                    PrintJob.build_plate_surface_id == surface.id,
                    PrintJob.status == PrintJobStatus.COMPLETED,
                    PrintJob.ended_at >= mesh_origin,
                )
            )
            or 0
        )
        due_at = mesh_origin + timedelta(days=plate.mesh_due_after_days)
        surface_statuses.append(
            {
                "surface_id": surface.id,
                "surface_code": surface.surface_code,
                "mesh_due": print_count >= plate.mesh_due_after_prints or now >= due_at,
                "prints_since": print_count,
                "due_at": due_at,
                "last_mesh_calibrated_at": last_mesh,
            }
        )
    return {
        "build_plate_id": plate.id,
        "cleaning_due": cleaning_prints >= plate.cleaning_due_after_prints or now >= cleaning_due_at,
        "cleaning_prints_since": cleaning_prints,
        "cleaning_due_at": cleaning_due_at,
        "last_cleaned_at": last_cleaned,
        "surfaces": surface_statuses,
    }


async def evaluate_operator_notifications(session: AsyncSession) -> int:
    """Converge every requested notification category from canonical state."""

    touched = 0
    category_keys: dict[str, set[str]] = {
        "moonraker_unavailable": set(),
        "projection_job_dead": set(),
        "spool_low": set(),
        "plate_maintenance_due": set(),
        "cura_deployment_failed": set(),
    }

    for printer in await session.scalars(select(Printer)):
        if printer.status == "unavailable":
            key = f"moonraker:{printer.id}:unavailable"
            category_keys["moonraker_unavailable"].add(key)
            await upsert_notification(
                session,
                deduplication_key=key,
                category="moonraker_unavailable",
                severity=NotificationSeverity.ERROR,
                title=f"{printer.name} is unavailable",
                message="Filament Manager cannot reach the assigned Moonraker service.",
                action_path="/diagnostics",
                object_type="printer",
                object_id=printer.id,
            )
            touched += 1

    for job in await session.scalars(select(OutboxJob).where(OutboxJob.status == JobStatus.DEAD)):
        key = f"outbox:{job.id}:dead"
        category_keys["projection_job_dead"].add(key)
        await upsert_notification(
            session,
            deduplication_key=key,
            category="projection_job_dead",
            severity=NotificationSeverity.ERROR,
            title="Integration job needs attention",
            message=f"{job.job_type} exhausted its retry limit.",
            action_path="/diagnostics",
            object_type="outbox_job",
            object_id=job.id,
        )
        touched += 1

    low_spools = await session.scalars(
        select(Spool).where(Spool.archived.is_(False), Spool.status.in_((SpoolStatus.LOW, SpoolStatus.EMPTY)))
    )
    for spool in low_spools:
        key = f"spool:{spool.id}:{spool.status.value}"
        category_keys["spool_low"].add(key)
        await upsert_notification(
            session,
            deduplication_key=key,
            category="spool_low",
            severity=(
                NotificationSeverity.ERROR
                if spool.status == SpoolStatus.EMPTY
                else NotificationSeverity.WARNING
            ),
            title=f"Spool {spool.spool_code} is {spool.status.value}",
            message=f"{spool.remaining_mass_effective_g} g remains on this spool.",
            action_path="/spools",
            object_type="spool",
            object_id=spool.id,
        )
        touched += 1

    for plate in await session.scalars(select(BuildPlate)):
        maintenance = await build_plate_maintenance_status(session, plate)
        if maintenance["cleaning_due"]:
            key = f"plate:{plate.id}:cleaning-due"
            category_keys["plate_maintenance_due"].add(key)
            await upsert_notification(
                session,
                deduplication_key=key,
                category="plate_maintenance_due",
                severity=NotificationSeverity.WARNING,
                title=f"{plate.display_name} needs cleaning",
                message="The configured print-count or day threshold has been reached.",
                action_path="/plates",
                object_type="build_plate",
                object_id=plate.id,
            )
            touched += 1
        surfaces = maintenance.get("surfaces")
        assert isinstance(surfaces, list)
        for surface in surfaces:
            assert isinstance(surface, dict)
            if surface["mesh_due"]:
                surface_id = surface["surface_id"]
                key = f"plate-surface:{surface_id}:mesh-due"
                category_keys["plate_maintenance_due"].add(key)
                await upsert_notification(
                    session,
                    deduplication_key=key,
                    category="plate_maintenance_due",
                    severity=NotificationSeverity.WARNING,
                    title=f"{surface['surface_code']} needs mesh calibration",
                    message="The configured print-count or day threshold has been reached.",
                    action_path="/plates",
                    object_type="build_plate_surface",
                    object_id=surface_id if isinstance(surface_id, UUID) else None,
                )
                touched += 1

    deployment_operation = func.coalesce(
        CuraDeployment.payload["operation"].as_string(),
        "material_library",
    )
    ranked_deployments = select(
        CuraDeployment.id.label("deployment_id"),
        func.row_number()
        .over(
            partition_by=(CuraDeployment.agent_id, deployment_operation),
            order_by=(CuraDeployment.created_at.desc(), CuraDeployment.id.desc()),
        )
        .label("deployment_rank"),
    ).subquery()
    failed_deployments = await session.execute(
        select(CuraDeployment, WorkstationAgent)
        .join(ranked_deployments, ranked_deployments.c.deployment_id == CuraDeployment.id)
        .join(WorkstationAgent, WorkstationAgent.id == CuraDeployment.agent_id)
        .where(
            ranked_deployments.c.deployment_rank == 1,
            CuraDeployment.status == CuraDeploymentStatus.FAILED,
        )
    )
    for deployment, agent in failed_deployments:
        notification_details = _cura_failure_notification(deployment, agent)
        if notification_details is None:
            continue
        key, title, message = notification_details
        category_keys["cura_deployment_failed"].add(key)
        await upsert_notification(
            session,
            deduplication_key=key,
            category="cura_deployment_failed",
            severity=NotificationSeverity.ERROR,
            title=title,
            message=message,
            action_path="/workstations",
            object_type="cura_deployment",
            object_id=deployment.id,
        )
        touched += 1

    for category, active_keys in category_keys.items():
        await _resolve_missing_category(session, category=category, active_keys=active_keys)
    await session.commit()
    return touched
