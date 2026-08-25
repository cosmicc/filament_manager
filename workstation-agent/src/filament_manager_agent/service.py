"""Polling service that discovers Cura and executes leased deployments."""

import platform
import time
from typing import Any

import httpx
import structlog

from . import __version__
from .apply import apply_rendered, managed_library_checksum, material_settings_sync_status
from .client import AgentClient
from .config import load_config
from .discovery import (
    acknowledge_managed_material_edits,
    cura_is_running,
    discover_installations,
    discover_managed_materials,
    discover_materials,
    discover_print_profiles,
    managed_material_edit_receipts,
    unmanaged_material_count,
)
from .nozzle import apply_nozzle_update
from .recovery import (
    capture_recovery_snapshot,
    material_settings_plugin_inventory,
    restore_recovery_snapshot,
)
from .render import render_deployment

logger = structlog.get_logger()


def _recovery_capture_message(error: BaseException | None = None, *, reason: object = None) -> str:
    """Return an actionable path-free recovery failure suitable for the server UI."""

    reason_messages = {
        "no_printer_configuration": "No Cura printer configuration was found to back up.",
        "suspected_reset": (
            "Cura appears to have been reset; the last known-good automatic backup was preserved."
        ),
        "deleted_by_administrator": "This automatic backup was previously deleted and remains suppressed.",
    }
    if isinstance(reason, str) and reason in reason_messages:
        return reason_messages[reason]
    message = str(error or "")
    if message in reason_messages.values():
        return message
    safe_messages = {
        "A supported Cura recovery directory is unsafe.": (
            "A supported Cura settings directory failed the local safety check."
        ),
        "A supported Cura recovery file is unsafe or oversized.": (
            "A supported Cura settings file failed the local safety or size check."
        ),
        "A supported Cura recovery file could not be read safely.": (
            "A supported Cura settings file could not be read safely."
        ),
        "A supported Cura configuration file is invalid.": (
            "A supported Cura settings file contains invalid syntax."
        ),
        "A supported Cura JSON configuration file is invalid.": (
            "A supported Cura JSON settings file contains invalid syntax."
        ),
        "A supported Cura JSON configuration file has an invalid root.": (
            "A supported Cura JSON settings file has an invalid structure."
        ),
        "Cura recovery settings exceed the safe capture limit.": (
            "The Cura settings backup exceeds the safe file or size limit."
        ),
    }
    return safe_messages.get(message, "Cura settings could not be captured safely on the workstation.")


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
        sync_status = material_settings_sync_status(installation.data_path)
        sync_status["plugins"] = material_settings_plugin_inventory(installation)
        report["material_settings_sync"] = sync_status
        installation_reports.append(report)
    materials = discover_materials(installations)
    print_profiles = discover_print_profiles(installations)
    managed_materials = discover_managed_materials(installations)
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
            "material_settings_verification_receipt": True,
            "authoritative_material_library": True,
            "hide_bundled_materials": True,
            "unmanaged_material_count": material_count,
            "unmanaged_material_file_count": material_file_count,
            "cura_print_profile_import": True,
            "unmanaged_print_profile_count": len(print_profiles),
            "managed_material_count": len(managed_materials),
            "unmanaged_import_source_count": len(import_sources),
            "cura_recovery_snapshots": True,
            "cura_recovery_capture_state": recovery_capture_state,
        },
        "cura_installations": installation_reports,
        "cura_materials": [source.report() for source in import_sources],
        "cura_managed_materials": [material.report() for material in managed_materials],
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
                recovery_error = _recovery_capture_message(error)
                logger.warning(
                    "recovery_capture_failed",
                    installation_id=installation.installation_id,
                    error_class=type(error).__name__,
                    message=str(error)[:500],
                )
    capture_state = "error" if recovery_error else "ready" if not running else "waiting_for_cura_close"
    edit_receipts = managed_material_edit_receipts(installations)
    client.heartbeat(
        heartbeat_payload(
            installations,
            recovery_error,
            recovery_capture_state=capture_state,
        )
    )
    if not running:
        acknowledge_managed_material_edits(edit_receipts)
    for snapshot in recovery_snapshots:
        try:
            client.upload_recovery_snapshot(snapshot)
        except (httpx.HTTPError, RuntimeError) as error:
            # Recovery is an independent capability. A rejected or unavailable
            # backup endpoint must never prevent managed materials, nozzles, or
            # restore claims from making progress.
            logger.warning(
                "recovery_snapshot_upload_failed",
                error_class=type(error).__name__,
                message="Cura settings backup upload failed; synchronization will continue.",
            )

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
    operation = claim.payload.get("operation")
    if operation == "recovery_capture":
        target = next(
            (
                installation
                for installation in installations
                if installation.installation_id == claim.payload.get("installation_id")
                and installation.version == claim.payload.get("cura_version")
            ),
            None,
        )
        if target is None:
            client.complete(
                claim.deployment_id,
                outcome="failed",
                result={},
                error_class="CuraNotDetected",
                error_message="The selected Cura installation is no longer available.",
            )
            return True
        try:
            snapshot = capture_recovery_snapshot(target)
            snapshot["capture_request_id"] = str(claim.deployment_id)
            response = client.upload_recovery_snapshot(snapshot)
            if response.get("accepted") is not True:
                raise RuntimeError(_recovery_capture_message(reason=response.get("reason")))
        except (OSError, RuntimeError, ValueError) as error:
            client.complete(
                claim.deployment_id,
                outcome="failed",
                result={},
                error_class=type(error).__name__,
                error_message=_recovery_capture_message(error),
            )
            logger.error(
                "manual_recovery_capture_failed",
                deployment_id=claim.deployment_id,
                error_class=type(error).__name__,
                message=str(error)[:500],
            )
            return True
        client.complete(
            claim.deployment_id,
            outcome="succeeded",
            result={"snapshot_id": response.get("snapshot_id"), "installation_id": target.installation_id},
        )
        logger.info("manual_recovery_capture_succeeded", deployment_id=claim.deployment_id)
        return True
    if operation == "nozzle_update":
        nozzle_results: list[dict[str, object]] = []
        nozzle_errors: list[dict[str, str]] = []
        for installation in installations:
            try:
                nozzle_results.append(
                    apply_nozzle_update(installation, str(claim.deployment_id), claim.payload)
                )
            except (OSError, RuntimeError, ValueError) as error:
                nozzle_errors.append(
                    {
                        "installation_id": installation.installation_id,
                        "error_class": type(error).__name__,
                        "message": str(error)[:500],
                    }
                )
        if nozzle_results:
            client.complete(
                claim.deployment_id,
                outcome="succeeded",
                result={
                    "installations": nozzle_results,
                    "unmatched_installations": nozzle_errors,
                },
            )
        else:
            client.complete(
                claim.deployment_id,
                outcome="failed",
                result={"installations": [], "errors": nozzle_errors},
                error_class=(nozzle_errors[0]["error_class"] if nozzle_errors else "CuraNotDetected"),
                error_message=(
                    nozzle_errors[0]["message"]
                    if nozzle_errors
                    else "No writable Cura user-data installation was detected."
                ),
            )
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
