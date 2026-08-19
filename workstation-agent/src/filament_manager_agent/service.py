"""Polling service that discovers Cura and executes leased deployments."""

import platform
import time
from typing import Any

import structlog

from . import __version__
from .apply import apply_rendered, managed_library_checksum
from .client import AgentClient
from .config import load_config
from .discovery import (
    cura_is_running,
    discover_installations,
    discover_managed_materials,
    discover_materials,
    discover_print_profiles,
    unmanaged_material_count,
)
from .recovery import capture_recovery_snapshot, restore_recovery_snapshot
from .render import render_deployment

logger = structlog.get_logger()


def heartbeat_payload(
    installations: list[Any],
    last_error: str | None = None,
    *,
    recovery_capture_state: str = "waiting_for_cura_close",
) -> dict[str, Any]:
    """Build bounded capability and discovery metadata."""

    installation_reports: list[dict[str, object]] = []
    for installation in installations:
        report = installation.report()
        report["managed_library_checksum"] = managed_library_checksum(installation.data_path)
        installation_reports.append(report)
    materials = discover_materials(installations)
    print_profiles = discover_print_profiles(installations)
    import_sources = [*materials[:100], *print_profiles[:100]]
    material_file_count = unmanaged_material_count(installations)
    # The takeover count must describe the rows actually sent to the server.  Cura
    # sources with no literal tracked values are still included because mapping them
    # to a template is a valid reviewed no-op and keeps the one-time takeover complete.
    material_count = len(materials)
    return {
        "agent_version": __version__,
        "capabilities": {
            "atomic_install": True,
            "automatic_backup": True,
            "rollback": True,
            "cura_process_guard": True,
            "material_profiles": True,
            "material_settings_plugin": True,
            "klipper_settings_plugin": True,
            "authoritative_material_library": True,
            "hide_bundled_materials": True,
            "unmanaged_material_count": material_count,
            "unmanaged_material_file_count": material_file_count,
            "cura_print_profile_import": True,
            "unmanaged_print_profile_count": len(print_profiles),
            "unmanaged_import_source_count": len(import_sources),
            "cura_recovery_snapshots": True,
            "cura_recovery_capture_state": recovery_capture_state,
        },
        "cura_installations": installation_reports,
        "cura_materials": [source.report() for source in import_sources],
        "cura_managed_materials": [
            material.report() for material in discover_managed_materials(installations)
        ],
        "last_error": last_error,
    }


def run_once() -> bool:
    """Report discovery and execute at most one leased deployment."""

    config = load_config()
    client = AgentClient(config)
    installations = discover_installations()
    running = cura_is_running()
    recovery_snapshots: list[dict[str, object]] = []
    recovery_error: str | None = None
    if not running:
        for installation in installations:
            try:
                recovery_snapshots.append(capture_recovery_snapshot(installation))
            except (OSError, RuntimeError, ValueError) as error:
                recovery_error = "Cura recovery capture failed; review the local agent log."
                logger.warning(
                    "recovery_capture_failed",
                    installation_id=installation.installation_id,
                    error_class=type(error).__name__,
                    message=str(error)[:500],
                )
    capture_state = "error" if recovery_error else "ready" if not running else "waiting_for_cura_close"
    client.heartbeat(
        heartbeat_payload(
            installations,
            recovery_error,
            recovery_capture_state=capture_state,
        )
    )
    for snapshot in recovery_snapshots:
        client.upload_recovery_snapshot(snapshot)

    recovery_claim = client.claim_recovery_restore()
    if recovery_claim is not None:
        if running:
            client.complete_recovery_restore(
                recovery_claim.restore_id,
                outcome="deferred",
                retry_after_seconds=60,
            )
            logger.info(
                "recovery_restore_deferred",
                restore_id=recovery_claim.restore_id,
                reason="cura_running",
            )
            return True
        target = next(
            (
                installation
                for installation in installations
                if installation.installation_id == recovery_claim.payload.get("installation_id")
                and installation.version == recovery_claim.payload.get("cura_version")
            ),
            None,
        )
        if target is None:
            client.complete_recovery_restore(recovery_claim.restore_id, outcome="failed")
            logger.error(
                "recovery_restore_failed",
                restore_id=recovery_claim.restore_id,
                reason="exact_cura_installation_unavailable",
            )
            return True
        try:
            recovery_result = restore_recovery_snapshot(
                target,
                str(recovery_claim.restore_id),
                recovery_claim.snapshot_checksum,
                recovery_claim.payload,
            )
        except (OSError, RuntimeError, ValueError) as error:
            client.complete_recovery_restore(recovery_claim.restore_id, outcome="failed")
            logger.error(
                "recovery_restore_failed",
                restore_id=recovery_claim.restore_id,
                error_class=type(error).__name__,
                message=str(error)[:500],
            )
            return True
        client.complete_recovery_restore(
            recovery_claim.restore_id,
            outcome="succeeded",
            result=recovery_result,
        )
        logger.info("recovery_restore_succeeded", restore_id=recovery_claim.restore_id)
        return True

    claim = client.claim()
    if claim is None:
        return False
    if running:
        client.complete(
            claim.deployment_id,
            outcome="deferred",
            result={"reason": "cura_running"},
            error_class="CuraRunning",
            error_message="Cura is open; the deployment will retry automatically after Cura closes.",
            retry_after_seconds=60,
        )
        logger.info("deployment_deferred", deployment_id=claim.deployment_id, reason="cura_running")
        return True
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for installation in installations:
        try:
            rendered = render_deployment(installation, claim.payload)
            results.append(
                apply_rendered(
                    installation,
                    str(claim.deployment_id),
                    claim.profile_checksum,
                    rendered,
                )
            )
        except (OSError, RuntimeError, ValueError) as error:
            errors.append(
                {
                    "installation_id": installation.installation_id,
                    "version": installation.version,
                    "error_class": type(error).__name__,
                    "message": str(error)[:500],
                }
            )
    if results:
        client.complete(
            claim.deployment_id,
            outcome="succeeded",
            result={"installations": results, "unmatched_installations": errors},
        )
        logger.info("deployment_succeeded", deployment_id=claim.deployment_id, installations=len(results))
        return True
    message = errors[0]["message"] if errors else "No writable Cura user-data installation was detected."
    client.complete(
        claim.deployment_id,
        outcome="failed",
        result={"installations": [], "errors": errors},
        error_class=errors[0]["error_class"] if errors else "CuraNotDetected",
        error_message=message,
    )
    logger.error("deployment_failed", deployment_id=claim.deployment_id, reason=message)
    return True


def run_forever() -> None:
    """Poll continuously with bounded delay and resilient structured error reporting."""

    config = load_config()
    logger.info(
        "agent_started",
        agent_code=config.agent_code,
        version=__version__,
        platform=platform.platform(),
    )
    while True:
        try:
            worked = run_once()
            delay = 2 if worked else config.poll_interval_seconds
        except Exception as error:  # The service must recover from transient server and filesystem failures.
            logger.error("agent_iteration_failed", error_class=type(error).__name__, message=str(error)[:500])
            delay = max(config.poll_interval_seconds, 15)
        time.sleep(delay)
