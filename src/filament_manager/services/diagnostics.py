"""Sanitized operational diagnostics and non-destructive recovery validation."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.clients.google_sheets import GoogleSheetsClient, GoogleSheetsError
from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.clients.spoolman import SpoolmanClient, SpoolmanError
from filament_manager.config import PrinterConfig, get_settings
from filament_manager.domain.cura_material_settings import CURA_MANAGED_SETTING_KEYS
from filament_manager.models.enums import CuraDeploymentStatus, JobStatus, NotificationSeverity
from filament_manager.models.inventory import (
    FilamentProduct,
    Printer,
    Spool,
    SpoolMeasurement,
    Vendor,
)
from filament_manager.models.operations import (
    Device,
    Notification,
    OutboxJob,
    ProjectionState,
    WorkerHeartbeat,
)
from filament_manager.models.workstations import CuraDeployment, CuraRecoveryRestore, WorkstationAgent
from filament_manager.services.cura_library import build_cura_library, queue_cura_library
from filament_manager.services.events import add_audit_event, add_outbox_job

EXPECTED_SCHEMA_VERSION = "a9b0c1d2e345"
SYSTEM_AGGREGATE_ID = UUID("00000000-0000-0000-0000-000000000001")

DATABASE_ERROR_CLASSES = {
    "DBAPIError",
    "DatabaseError",
    "IntegrityError",
    "MissingGreenlet",
    "OperationalError",
    "ProgrammingError",
    "SQLAlchemyError",
}


def _check(
    key: str,
    label: str,
    category: str,
    status: str,
    detail: str,
    checked_at: datetime,
) -> dict[str, object]:
    """Build one bounded diagnostic check payload."""

    return {
        "key": key[:96],
        "label": label[:160],
        "category": category[:48],
        "status": status[:32],
        "detail": detail[:500],
        "checked_at": checked_at,
    }


def _cura_material_settings_check(
    agent: WorkstationAgent,
    installation: dict[str, object],
    checked_at: datetime,
) -> dict[str, object]:
    """Describe one workstation's value-free Cura settings verification receipt."""

    version = installation.get("version")
    safe_version = str(version)[:32] if isinstance(version, str) else "unknown"
    sync = installation.get("material_settings_sync")
    if not agent.enabled or not agent.cura_management_enabled:
        detail = (
            "Agent is disabled"
            if not agent.enabled
            else "Verification begins after the one-time Cura material-library takeover"
        )
        return _check(
            f"cura.material_settings.{agent.id}.{installation.get('installation_id', 'unknown')}",
            f"Cura {safe_version} material print settings · {agent.display_name}",
            "synchronization",
            "disabled",
            detail,
            checked_at,
        )
    if not isinstance(sync, dict):
        return _check(
            f"cura.material_settings.{agent.id}.{installation.get('installation_id', 'unknown')}",
            f"Cura {safe_version} material print settings · {agent.display_name}",
            "synchronization",
            "warning",
            (
                "No verification receipt has been reported. Upgrade and restart the "
                "workstation agent, then open Cura once."
            ),
            checked_at,
        )
    receipt_status = sync.get("status")
    expected = sync.get("expected_count") if isinstance(sync.get("expected_count"), int) else 0
    exposed = sync.get("exposed_count") if isinstance(sync.get("exposed_count"), int) else 0
    raw_missing = sync.get("missing_keys")
    missing = (
        [key for key in raw_missing if isinstance(key, str) and key in CURA_MANAGED_SETTING_KEYS]
        if isinstance(raw_missing, list)
        else []
    )
    plugin_ready = sync.get("material_settings_plugin_ready") is True
    klipper_ready = sync.get("klipper_settings_plugin_ready") is True
    if receipt_status == "healthy" and expected == exposed and plugin_ready and klipper_ready:
        status = "healthy"
        detail = (
            f"{exposed} of {expected} required material print settings are exposed and enforced; "
            "Material Settings and Klipper Settings are ready"
        )
    elif receipt_status in {"waiting_for_cura", "waiting_for_machine", "not_deployed"}:
        status = "warning"
        detail = (
            f"{expected} required settings are deployed but not yet verified. "
            "Open or restart Cura with the configured printer active."
        )
    elif receipt_status == "invalid":
        status = "error"
        detail = (
            "The workstation reported an invalid settings receipt; upgrade and restart its agent and Cura."
        )
    else:
        status = "error"
        missing_detail = ", ".join(missing[:12]) or "none reported"
        detail = (
            f"{exposed} of {expected} required settings are exposed. Missing: {missing_detail}. "
            f"Material Settings ready: {'yes' if plugin_ready else 'no'}; "
            f"Klipper Settings ready: {'yes' if klipper_ready else 'no'}."
        )
    return _check(
        f"cura.material_settings.{agent.id}.{installation.get('installation_id', 'unknown')}",
        f"Cura {safe_version} material print settings · {agent.display_name}",
        "synchronization",
        status,
        detail,
        checked_at,
    )


def _sanitized_error_detail(error_class: str | None, detail: str | None) -> str | None:
    """Return bounded operator guidance without SQL, URLs, or upstream response content."""

    if not detail:
        return None
    normalized = " ".join(detail.split())
    if error_class in DATABASE_ERROR_CLASSES or any(
        marker in normalized for marker in ("[SQL:", "psycopg.errors.", "sqlalche.me/e/", "Traceback (")
    ):
        return "A database operation failed. Review the server worker log for the matching time."
    if "http://" in normalized or "https://" in normalized:
        return "An external integration request failed. Review the server worker log for the matching time."
    return normalized[:500]


def diagnostics_text(overview: dict[str, object]) -> str:
    """Render one sanitized operational overview as a portable plain-text report."""

    checked_at = cast(datetime, overview["checked_at"])
    checks = cast(list[dict[str, object]], overview["checks"])
    queue_counts = cast(dict[str, int], overview["queue_counts"])
    job_type_counts = cast(dict[str, int], overview["job_type_counts"])
    failure_groups = cast(list[dict[str, object]], overview.get("failure_groups", []))
    error_log = cast(list[dict[str, object]], overview["error_log"])
    lines = [
        "Filament Manager diagnostics",
        f"Generated: {checked_at.isoformat()}",
        "This bounded export excludes credentials, configured URLs, upstream response bodies, "
        "SQL, and tracebacks.",
        "",
        "Checks",
        "------",
    ]
    for check in checks:
        status = str(check["status"]).upper()
        lines.extend(
            [
                f"[{status}] {check['label']} ({check['category']})",
                f"  {check['detail']}",
                f"  Checked: {cast(datetime, check['checked_at']).isoformat()}",
            ]
        )
    lines.extend(["", "Projection queue", "----------------"])
    if queue_counts:
        lines.extend(f"{key}: {value}" for key, value in sorted(queue_counts.items()))
    else:
        lines.append("No queued work has been recorded.")
    lines.extend(["", "Active job types", "----------------"])
    if job_type_counts:
        lines.extend(f"{key}: {value}" for key, value in sorted(job_type_counts.items()))
    else:
        lines.append("No pending, running, failed, or dead job types.")
    lines.extend(["", "Active projection failures", "--------------------------"])
    if failure_groups:
        for failure in failure_groups:
            occurred_at = cast(datetime, failure["occurred_at"])
            lines.extend(
                [
                    f"{failure['job_type']}: {failure['count']} actionable failure(s)",
                    (
                        f"  Latest: {failure['status']} after {failure['attempts']}/"
                        f"{failure['max_attempts']} attempts · {failure['error_class']}"
                    ),
                    f"  Occurred: {occurred_at.isoformat()}",
                    f"  Detail: {failure.get('detail') or 'No additional detail retained.'}",
                ]
            )
    else:
        lines.append("No active projection failures.")
    lines.extend(["", "Recent errors", "-------------"])
    if error_log:
        for entry in error_log:
            occurred_at = cast(datetime, entry["occurred_at"])
            lines.extend(
                [
                    (
                        f"[{str(entry['severity']).upper()}] {entry['summary']}"
                        if entry.get("current", True)
                        else f"[HISTORY {str(entry['severity']).upper()}] {entry['summary']}"
                    ),
                    f"  Source: {entry['source']}",
                    f"  Occurred: {occurred_at.isoformat()}",
                    f"  Detail: {entry.get('detail') or 'No additional detail retained.'}",
                ]
            )
    else:
        lines.append("No recent operational errors.")
    return "\n".join(lines) + "\n"


async def _connection_checks(checked_at: datetime) -> list[dict[str, object]]:
    """Check configured APIs concurrently while retaining sanitized failures only."""

    settings = get_settings()

    async def spoolman() -> dict[str, object]:
        try:
            await SpoolmanClient(settings.spoolman).projection_health()
            return _check(
                "spoolman.connection",
                "Spoolman",
                "connection",
                "healthy",
                "API and managed projection fields are ready",
                checked_at,
            )
        except SpoolmanError:
            return _check(
                "spoolman.connection",
                "Spoolman",
                "connection",
                "error",
                "API or managed projection-field validation failed",
                checked_at,
            )

    async def moonraker(configured: PrinterConfig) -> dict[str, object]:
        try:
            await MoonrakerClient(configured).health()
            return _check(
                f"moonraker.{configured.id}",
                f"Moonraker · {configured.name}",
                "connection",
                "healthy",
                "Moonraker is reachable",
                checked_at,
            )
        except MoonrakerError:
            return _check(
                f"moonraker.{configured.id}",
                f"Moonraker · {configured.name}",
                "connection",
                "error",
                "Moonraker health validation failed",
                checked_at,
            )

    async def google() -> dict[str, object]:
        if not settings.google.enabled:
            return _check(
                "google.connection",
                "Google Sheets",
                "connection",
                "disabled",
                "Publication is disabled",
                checked_at,
            )
        assert settings.google.spreadsheet_id
        try:
            await GoogleSheetsClient(
                settings.google.spreadsheet_id,
                settings.google.service_account_file,
                settings.google.resolved_service_account_info(),
            ).health()
            return _check(
                "google.connection",
                "Google Sheets",
                "connection",
                "healthy",
                "Publication workbook is reachable",
                checked_at,
            )
        except (GoogleSheetsError, ValueError):
            return _check(
                "google.connection",
                "Google Sheets",
                "connection",
                "error",
                "Publication workbook validation failed",
                checked_at,
            )

    pending = [spoolman(), google()]
    pending.extend(moonraker(config) for config in settings.moonraker.printers)
    return list(await asyncio.gather(*pending))


async def operational_overview(session: AsyncSession) -> dict[str, object]:
    """Collect connections, synchronization freshness, workers, queues, and bounded errors."""

    checked_at = datetime.now(UTC)
    checks = await _connection_checks(checked_at)
    schema_result = await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
    schema_version = schema_result.scalar_one_or_none()
    checks.append(
        _check(
            "database.schema",
            "Canonical PostgreSQL",
            "connection",
            "healthy" if schema_version == EXPECTED_SCHEMA_VERSION else "warning",
            (
                f"Schema is current at {schema_version}"
                if schema_version == EXPECTED_SCHEMA_VERSION
                else f"Schema is {schema_version or 'unavailable'}; expected {EXPECTED_SCHEMA_VERSION}"
            ),
            checked_at,
        )
    )

    actionable_statuses = (
        JobStatus.PENDING,
        JobStatus.RUNNING,
        JobStatus.FAILED,
        JobStatus.DEAD,
    )
    queue_rows = await session.execute(
        select(OutboxJob.status, func.count(OutboxJob.id))
        .where(OutboxJob.status.in_(actionable_statuses))
        .group_by(OutboxJob.status)
    )
    queue_counts = {status.value: int(count) for status, count in queue_rows}
    for actionable_status in actionable_statuses:
        queue_counts.setdefault(actionable_status.value, 0)
    job_rows = await session.execute(
        select(OutboxJob.job_type, func.count(OutboxJob.id))
        .where(OutboxJob.status.in_(actionable_statuses))
        .group_by(OutboxJob.job_type)
    )
    job_type_counts = {job_type: int(count) for job_type, count in job_rows}
    dead = queue_counts.get(JobStatus.DEAD.value, 0)
    failed = queue_counts.get(JobStatus.FAILED.value, 0)
    retrying_pending, next_retry_at = (
        await session.execute(
            select(func.count(OutboxJob.id), func.min(OutboxJob.next_attempt_at)).where(
                OutboxJob.status == JobStatus.PENDING,
                OutboxJob.attempts > 0,
            )
        )
    ).one()
    retrying_pending = int(retrying_pending)
    retry_detail = (
        f"; {retrying_pending} retrying after an earlier failure"
        + (f", next retry {next_retry_at.isoformat()}" if next_retry_at is not None else "")
        if retrying_pending
        else ""
    )
    checks.append(
        _check(
            "outbox.queue",
            "Projection queue",
            "worker",
            "error" if dead else "warning" if failed or retrying_pending else "healthy",
            (
                f"{queue_counts.get('pending', 0)} pending, {queue_counts.get('running', 0)} running, "
                f"{failed} failed, {dead} dead{retry_detail}"
            ),
            checked_at,
        )
    )

    heartbeat_rows = list(
        await session.scalars(
            select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()).limit(100)
        )
    )
    live_cutoff = checked_at - timedelta(seconds=30)
    live_heartbeats = [item for item in heartbeat_rows if item.last_seen_at >= live_cutoff]
    expected_dispatchers = get_settings().sync.outbox_workers
    live_dispatchers = [item for item in live_heartbeats if item.worker_type == "dispatcher"]
    live_schedulers = [item for item in live_heartbeats if item.worker_type == "scheduler"]
    checks.append(
        _check(
            "workers.dispatchers",
            "Outbox dispatchers",
            "worker",
            "healthy" if len(live_dispatchers) >= expected_dispatchers else "error",
            f"{len(live_dispatchers)} of {expected_dispatchers} configured dispatchers reporting",
            checked_at,
        )
    )
    checks.append(
        _check(
            "workers.scheduler",
            "Periodic scheduler",
            "worker",
            "healthy" if live_schedulers else "error",
            f"{len(live_schedulers)} scheduler heartbeat{'s' if len(live_schedulers) != 1 else ''} reporting",
            checked_at,
        )
    )
    for heartbeat in live_heartbeats:
        checks.append(
            _check(
                f"worker.{heartbeat.worker_id}",
                f"{heartbeat.worker_type.title()} · {heartbeat.hostname}",
                "worker",
                "error" if heartbeat.status == "error" else "healthy",
                (
                    f"{heartbeat.status.title()}"
                    + (f" · {heartbeat.current_job_type}" if heartbeat.current_job_type else "")
                    + f" · last heartbeat {heartbeat.last_seen_at.isoformat()}"
                ),
                checked_at,
            )
        )
    printers = list(await session.scalars(select(Printer).order_by(Printer.name)))
    for printer in printers:
        state_fresh = printer.last_seen_at is not None and printer.last_seen_at >= checked_at - timedelta(
            minutes=2
        )
        history_fresh = (
            printer.last_print_history_sync_at is not None
            and printer.last_print_history_sync_at >= checked_at - timedelta(minutes=2)
        )
        info_fresh = (
            printer.last_info_sync_at is not None
            and printer.last_info_sync_at >= checked_at - timedelta(minutes=10)
        )
        checks.extend(
            [
                _check(
                    f"printer.{printer.id}.state",
                    f"{printer.name} state synchronization",
                    "synchronization",
                    "healthy" if state_fresh else "warning",
                    f"Last successful state synchronization: {printer.last_seen_at or 'never'}",
                    checked_at,
                ),
                _check(
                    f"printer.{printer.id}.history",
                    f"{printer.name} print-history synchronization",
                    "synchronization",
                    "healthy" if history_fresh else "warning",
                    "Last successful history synchronization: "
                    f"{printer.last_print_history_sync_at or 'never'}",
                    checked_at,
                ),
                _check(
                    f"printer.{printer.id}.information",
                    f"{printer.name} information synchronization",
                    "synchronization",
                    "healthy" if info_fresh else "warning",
                    f"Last successful information synchronization: {printer.last_info_sync_at or 'never'}",
                    checked_at,
                ),
                _check(
                    f"printer.{printer.id}.nozzle",
                    f"{printer.name} physical nozzle",
                    "operational",
                    "healthy" if printer.active_nozzle_id else "warning",
                    (
                        "Physical nozzle is assigned"
                        if printer.active_nozzle_id
                        else "No physical nozzle is assigned"
                    ),
                    checked_at,
                ),
                _check(
                    f"printer.{printer.id}.spool_preflight",
                    f"{printer.name} spool preflight catalog",
                    "synchronization",
                    (
                        "healthy"
                        if printer.spool_preflight_status == "healthy"
                        else "warning"
                        if printer.spool_preflight_status in {"unknown", "not_installed", "restoring"}
                        else "error"
                    ),
                    printer.spool_preflight_message
                    or (
                        "Last successful catalog synchronization: "
                        f"{printer.last_spool_preflight_sync_at or 'never'}"
                    ),
                    checked_at,
                ),
            ]
        )

    agents = list(await session.scalars(select(WorkstationAgent).order_by(WorkstationAgent.display_name)))
    for agent in agents:
        fresh = agent.last_seen_at is not None and agent.last_seen_at >= checked_at - timedelta(minutes=2)
        agent_status = (
            "disabled"
            if not agent.enabled
            else "error"
            if agent.last_error
            else "healthy"
            if fresh
            else "warning"
        )
        checks.append(
            _check(
                f"cura.{agent.id}",
                f"Cura agent · {agent.display_name}",
                "synchronization",
                agent_status,
                (
                    "Agent is disabled"
                    if not agent.enabled
                    else agent.last_error
                    if agent.last_error
                    else f"Last contact: {agent.last_seen_at}"
                    if fresh
                    else (
                        f"No recent contact; last contact was {agent.last_seen_at}. "
                        "Verify the workstation service is running and upgraded."
                        if agent.last_seen_at
                        else "The agent has never contacted the server; verify pairing and service state."
                    )
                ),
                checked_at,
            )
        )
        for installation in agent.cura_installations:
            if isinstance(installation, dict):
                checks.append(_cura_material_settings_check(agent, installation, checked_at))
        recovery_status = agent.cura_recovery_status
        checks.append(
            _check(
                f"cura.recovery.{agent.id}",
                f"Cura recovery · {agent.display_name}",
                "recovery",
                (
                    "healthy"
                    if recovery_status == "ready"
                    else "error"
                    if recovery_status == "restore_failed"
                    else "warning"
                ),
                (
                    agent.cura_recovery_message
                    or (
                        f"Latest safe snapshot: {agent.last_recovery_snapshot_at}"
                        if agent.last_recovery_snapshot_at
                        else "No operational Cura recovery point has been captured yet"
                    )
                ),
                checked_at,
            )
        )

    failure_statuses = (
        JobStatus.PENDING,
        JobStatus.RUNNING,
        JobStatus.FAILED,
        JobStatus.DEAD,
    )
    failure_count_rows = await session.execute(
        select(OutboxJob.job_type, func.count(OutboxJob.id))
        .where(
            OutboxJob.status.in_(failure_statuses),
            OutboxJob.last_error_class.is_not(None),
        )
        .group_by(OutboxJob.job_type)
    )
    failure_counts = {job_type: int(count) for job_type, count in failure_count_rows}
    ranked_failures = (
        select(
            OutboxJob.id.label("job_id"),
            func.row_number()
            .over(
                partition_by=OutboxJob.job_type,
                order_by=(
                    OutboxJob.last_error_at.desc().nullslast(),
                    OutboxJob.created_at.desc(),
                ),
            )
            .label("failure_rank"),
        )
        .where(
            OutboxJob.status.in_(failure_statuses),
            OutboxJob.last_error_class.is_not(None),
        )
        .subquery()
    )
    latest_failures = list(
        await session.scalars(
            select(OutboxJob)
            .join(ranked_failures, ranked_failures.c.job_id == OutboxJob.id)
            .where(ranked_failures.c.failure_rank == 1)
            .order_by(OutboxJob.job_type)
        )
    )
    failure_groups = [
        {
            "job_type": job.job_type,
            "count": failure_counts[job.job_type],
            "status": job.status.value,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "error_class": job.last_error_class or "UnknownError",
            "detail": _sanitized_error_detail(job.last_error_class, job.last_error_message),
            "occurred_at": job.last_error_at or job.created_at,
        }
        for job in latest_failures
    ]

    active_errors = list(
        await session.scalars(
            select(Notification)
            .where(
                Notification.active.is_(True),
                Notification.severity == NotificationSeverity.ERROR,
            )
            .order_by(Notification.last_seen_at.desc())
            .limit(10)
        )
    )
    active_cura_deployment_ids = set(
        await session.scalars(
            select(Notification.object_id).where(
                Notification.active.is_(True),
                Notification.severity == NotificationSeverity.ERROR,
                Notification.object_type == "cura_deployment",
                Notification.object_id.is_not(None),
            )
        )
    )
    error_log: list[dict[str, object]] = []
    failed_jobs = list(
        await session.scalars(
            select(OutboxJob)
            .where(
                OutboxJob.status.in_(failure_statuses),
                OutboxJob.last_error_class.is_not(None),
            )
            .order_by(OutboxJob.last_error_at.desc().nullslast(), OutboxJob.created_at.desc())
            .limit(15)
        )
    )
    for job in failed_jobs:
        error_log.append(
            {
                "source": "Projection worker",
                "severity": "error" if job.status == JobStatus.DEAD else "warning",
                "summary": f"{job.job_type} · {job.last_error_class}",
                "detail": _sanitized_error_detail(job.last_error_class, job.last_error_message),
                "occurred_at": job.last_error_at or job.created_at,
                "correlation_id": None,
                "current": True,
            }
        )
    failed_deployments = list(
        await session.scalars(
            select(CuraDeployment)
            .where(CuraDeployment.last_error_class.is_not(None))
            .order_by(CuraDeployment.updated_at.desc())
            .limit(10)
        )
    )
    for deployment in failed_deployments:
        operation = deployment.operation
        source = (
            "Cura backup request"
            if operation == "recovery_capture"
            else "Cura nozzle synchronization"
            if operation == "nozzle_update"
            else "Cura material synchronization"
        )
        error_log.append(
            {
                "source": source,
                "severity": "error" if deployment.status == CuraDeploymentStatus.FAILED else "warning",
                "summary": f"{deployment.last_error_class or 'Deployment error'}",
                "detail": _sanitized_error_detail(
                    deployment.last_error_class,
                    deployment.last_error_message,
                ),
                "occurred_at": deployment.updated_at,
                "correlation_id": None,
                "current": deployment.id in active_cura_deployment_ids,
            }
        )
    failed_restores = list(
        await session.scalars(
            select(CuraRecoveryRestore)
            .where(CuraRecoveryRestore.last_error_class.is_not(None))
            .order_by(CuraRecoveryRestore.updated_at.desc())
            .limit(10)
        )
    )
    for restore in failed_restores:
        error_log.append(
            {
                "source": "Cura recovery",
                "severity": "error" if restore.status == CuraDeploymentStatus.FAILED else "warning",
                "summary": f"{restore.last_error_class or 'Recovery error'}",
                "detail": _sanitized_error_detail(
                    restore.last_error_class,
                    restore.last_error_message,
                ),
                "occurred_at": restore.updated_at,
                "correlation_id": None,
                "current": False,
            }
        )
    for notification in active_errors:
        if notification.object_type == "cura_deployment":
            # The deployment record above retains the specific sanitized cause;
            # avoid repeating its generic operator notification in the log.
            continue
        error_log.append(
            {
                "source": "Operator notification",
                "severity": "error",
                "summary": notification.title,
                "detail": notification.message,
                "occurred_at": notification.last_seen_at,
                "correlation_id": None,
                "current": True,
            }
        )
    error_log.sort(key=lambda item: cast(datetime, item["occurred_at"]), reverse=True)
    return {
        "checked_at": checked_at,
        "checks": checks,
        "queue_counts": queue_counts,
        "job_type_counts": job_type_counts,
        "failure_groups": failure_groups,
        "error_log": error_log[:25],
    }


async def run_recovery_validation(session: AsyncSession) -> dict[str, object]:
    """Run non-destructive backup/recovery readiness and integrity checks."""

    overview = await operational_overview(session)
    checked_at = datetime.now(UTC)
    checks = list(cast(list[dict[str, object]], overview["checks"]))

    measurement_errors = (
        await session.scalar(
            select(func.count(SpoolMeasurement.id)).where(
                SpoolMeasurement.net_mass_g != SpoolMeasurement.gross_mass_g - SpoolMeasurement.tare_mass_g
            )
        )
        or 0
    )
    checks.append(
        _check(
            "integrity.measurements",
            "Measurement integrity",
            "recovery",
            "healthy" if measurement_errors == 0 else "error",
            f"{measurement_errors} inconsistent immutable measurement records",
            checked_at,
        )
    )
    invalid_credentials = (
        await session.scalar(
            select(func.count(Device.id)).where(
                Device.enabled.is_(True), func.length(Device.credential_hash) != 64
            )
        )
        or 0
    )
    checks.append(
        _check(
            "integrity.device_credentials",
            "Device credential integrity",
            "recovery",
            "healthy" if invalid_credentials == 0 else "error",
            f"{invalid_credentials} enabled devices have invalid credential hashes",
            checked_at,
        )
    )

    orphaned = 0
    lagging = 0
    states = list(
        await session.scalars(
            select(ProjectionState).where(
                ProjectionState.system == "spoolman",
                ProjectionState.object_type.in_(("vendor", "filament_product", "spool")),
            )
        )
    )
    for state in states:
        record_version: int | None = None
        if state.object_type == "vendor":
            record = await session.get(Vendor, state.object_id)
            record_version = record.record_version if record else None
        elif state.object_type == "filament_product":
            product = await session.get(FilamentProduct, state.object_id)
            record_version = product.record_version if product else None
        else:
            spool = await session.get(Spool, state.object_id)
            record_version = spool.record_version if spool else None
        if record_version is None:
            orphaned += 1
        elif state.acknowledged_version is None or state.acknowledged_version < record_version:
            lagging += 1
    checks.extend(
        [
            _check(
                "integrity.orphan_projections",
                "Orphan projection state",
                "recovery",
                "healthy" if orphaned == 0 else "error",
                f"{orphaned} projection records reference missing canonical objects",
                checked_at,
            ),
            _check(
                "integrity.projection_lag",
                "Spoolman projection consistency",
                "recovery",
                "healthy" if lagging == 0 else "warning",
                f"{lagging} canonical records are newer than their acknowledged projection",
                checked_at,
            ),
        ]
    )

    managed_agents = list(
        await session.scalars(
            select(WorkstationAgent).where(
                WorkstationAgent.enabled.is_(True), WorkstationAgent.cura_management_enabled.is_(True)
            )
        )
    )
    missing_deployments = 0
    if managed_agents:
        try:
            library = await build_cura_library(session)
            checksum = str(library["library_checksum"])
            for agent in managed_agents:
                succeeded = await session.scalar(
                    select(CuraDeployment.id).where(
                        CuraDeployment.agent_id == agent.id,
                        CuraDeployment.profile_checksum == checksum,
                        CuraDeployment.status == CuraDeploymentStatus.SUCCEEDED,
                    )
                )
                missing_deployments += int(succeeded is None)
        except ValueError:
            missing_deployments = len(managed_agents)
    checks.append(
        _check(
            "integrity.cura_deployments",
            "Current Cura library deployments",
            "recovery",
            "healthy" if missing_deployments == 0 else "warning",
            f"{missing_deployments} managed workstations lack the current successful library",
            checked_at,
        )
    )
    recovery_ready = sum(
        agent.cura_recovery_status == "ready" and agent.last_recovery_snapshot_at is not None
        for agent in managed_agents
    )
    checks.append(
        _check(
            "integrity.cura_recovery_snapshots",
            "Cura workstation recovery points",
            "recovery",
            "healthy" if recovery_ready == len(managed_agents) else "warning",
            f"{recovery_ready} of {len(managed_agents)} managed workstations have a current safe snapshot",
            checked_at,
        )
    )

    summary = {
        "healthy": sum(check["status"] == "healthy" for check in checks),
        "warning": sum(check["status"] == "warning" for check in checks),
        "error": sum(check["status"] == "error" for check in checks),
        "disabled": sum(check["status"] == "disabled" for check in checks),
    }
    return {"summary": summary, "checks": checks, "completed_at": checked_at}


async def queue_projection_rebuild(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    correlation_id: str,
) -> dict[str, object]:
    """Queue supported projection reconstruction without changing canonical records."""

    settings = get_settings()
    now = datetime.now(UTC)
    # Outbox aggregate versions are signed 32-bit integers. The request hash
    # preserves idempotency uniqueness without overflowing that contract.
    version = int(now.timestamp()) % 2_000_000_000
    request_token = hashlib.sha256(correlation_id.encode("utf-8")).hexdigest()[:16]
    categories = {"spoolman": 1, "google": 0, "cura": 0}
    add_outbox_job(
        session,
        job_type="spoolman.reconcile.full",
        idempotency_key=f"diagnostic-rebuild:spoolman:{version}:{request_token}",
        aggregate_type="system",
        aggregate_id=SYSTEM_AGGREGATE_ID,
        aggregate_version=version,
        payload={"requested_at": now.isoformat()},
    )
    if settings.google.enabled:
        add_outbox_job(
            session,
            job_type="google.rebuild.full",
            idempotency_key=f"diagnostic-rebuild:google:{version}:{request_token}",
            aggregate_type="system",
            aggregate_id=SYSTEM_AGGREGATE_ID,
            aggregate_version=version,
            payload={"requested_at": now.isoformat()},
        )
        categories["google"] = 1
    agents = list(
        await session.scalars(
            select(WorkstationAgent).where(
                WorkstationAgent.enabled.is_(True), WorkstationAgent.cura_management_enabled.is_(True)
            )
        )
    )
    if agents:
        try:
            deployments = await queue_cura_library(session, agents, requested_by=actor_id, force=True)
            categories["cura"] = len(deployments)
        except ValueError:
            categories["cura"] = 0
    add_audit_event(
        session,
        actor_id=actor_id,
        source="web" if actor_id else "cli",
        action="diagnostics.projections.rebuild",
        object_type="system",
        object_id=None,
        before=None,
        after=cast(dict[str, object], categories),
        correlation_id=correlation_id[:64],
    )
    await session.commit()
    return {
        "status": "queued",
        "queued_jobs": sum(categories.values()),
        "categories": categories,
    }
