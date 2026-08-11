"""Operator commands for pairing, discovery, service execution, and rollback."""

import json
import platform
from typing import Annotated
from urllib.parse import urlparse

import structlog
import typer

from . import __version__
from .apply import rollback as rollback_deployment
from .client import pair_agent
from .config import load_config, save_config
from .discovery import discover_installations, platform_key
from .models import AgentConfig
from .service import heartbeat_payload, run_forever, run_once

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )


def _validate_server_url(value: str, allow_http: bool) -> str:
    parsed = urlparse(value)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise typer.BadParameter("Use an absolute HTTP(S) URL without embedded credentials.")
    if parsed.scheme != "https" and not (allow_http and loopback):
        raise typer.BadParameter("HTTPS is required. --allow-http is limited to loopback development.")
    return value.rstrip("/")


@app.command()
def pair(
    server: Annotated[str, typer.Option(help="Filament Manager public base URL")],
    code: Annotated[str, typer.Option(prompt=True, hide_input=True, help="One-time pairing code")],
    name: Annotated[str, typer.Option(prompt="Workstation name", help="Name shown in Filament Manager")],
    allow_http: Annotated[bool, typer.Option(help="Allow loopback HTTP for local development only")] = False,
) -> None:
    """Pair this user account to Filament Manager once."""

    server_url = _validate_server_url(server, allow_http)
    installations = discover_installations()
    payload = {
        "pairing_code": code,
        "display_name": name.strip(),
        "hostname": platform.node() or "unknown-workstation",
        "platform": platform_key(),
        "architecture": platform.machine() or "unknown",
        **heartbeat_payload(installations),
    }
    payload.pop("last_error", None)
    response = pair_agent(server_url, payload)
    config = AgentConfig.model_validate(
        {
            "server_url": server_url,
            "agent_id": str(response["agent_id"]),
            "agent_code": str(response["agent_code"]),
            "agent_token": str(response["agent_token"]),
            "display_name": name.strip(),
        }
    )
    save_config(config)
    typer.echo(
        f"Paired {config.agent_code}. The scoped credential is stored in the current user's private config."
    )


@app.command("scan")
def scan_cura() -> None:
    """Show sanitized Cura discovery and machine matching inputs."""

    typer.echo(json.dumps([item.report() for item in discover_installations()], indent=2))


@app.command("run-once")
def run_single_iteration() -> None:
    """Heartbeat and process at most one deployment."""

    _configure_logging()
    run_once()


@app.command()
def run() -> None:
    """Run the persistent polling service."""

    _configure_logging()
    run_forever()


@app.command()
def status() -> None:
    """Show non-secret pairing and local Cura discovery state."""

    config = load_config()
    typer.echo(f"Agent: {config.agent_code} ({config.display_name})")
    typer.echo(f"Server: {str(config.server_url).rstrip('/')}")
    typer.echo(f"Version: {__version__}")
    typer.echo(f"Detected Cura installations: {len(discover_installations())}")


@app.command()
def rollback(deployment_id: str) -> None:
    """Restore the automatic backup for one deployment."""

    restored = rollback_deployment(deployment_id)
    typer.echo(f"Restored: {', '.join(restored)}")


if __name__ == "__main__":
    app()
