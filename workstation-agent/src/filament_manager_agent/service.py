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
from .render import render_deployment

logger = structlog.get_logger()


def heartbeat_payload(
    installations: list[Any],
    last_error: str | None = None,
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
    material_count = unmanaged_material_count(installations)
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
            "cura_print_profile_import": True,
            "unmanaged_print_profile_count": len(print_profiles),
            "unmanaged_import_source_count": material_count + len(print_profiles),
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
    client.heartbeat(heartbeat_payload(installations))
    claim = client.claim()
    if claim is None:
        return False
    if cura_is_running():
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
