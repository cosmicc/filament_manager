"""Administrative first-run, seed, and workbook-import commands."""

import asyncio
import json
import time
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from filament_manager.config import get_settings
from filament_manager.database import get_session_factory
from filament_manager.services.diagnostics import queue_projection_rebuild, run_recovery_validation
from filament_manager.services.seed import seed_configured_system
from filament_manager.services.workbook_import import commit_approved_run, save_dry_run

app = typer.Typer(no_args_is_help=True, help="Filament Manager administrative commands")


@app.command("seed-system")
def seed_system() -> None:
    """Idempotently seed the initial P1-P5 set and configured printers."""

    async def command() -> None:
        settings = get_settings()
        async with get_session_factory()() as session:
            await seed_configured_system(session, settings)
            await session.commit()
            typer.echo("Seeded configured printers and P1-P5")

    asyncio.run(command())


@app.command("verify")
def verify_recovery_readiness() -> None:
    """Run non-destructive database, integration, projection, and recovery checks."""

    async def command() -> None:
        async with get_session_factory()() as session:
            results = await run_recovery_validation(session)
            typer.echo(json.dumps(results, indent=2, default=str))
            summary = results.get("summary", {})
            if isinstance(summary, dict) and int(summary.get("error", 0)):
                raise typer.Exit(code=1)

    asyncio.run(command())


@app.command("rebuild-projections")
def rebuild_projections(
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm that all supported external projections may be queued"),
    ] = False,
) -> None:
    """Queue a complete Spoolman, Google, and managed-Cura projection rebuild."""

    if not confirm:
        raise typer.BadParameter("pass --confirm to queue the projection rebuild")

    async def command() -> None:
        async with get_session_factory()() as session:
            result = await queue_projection_rebuild(
                session,
                actor_id=None,
                correlation_id=f"cli-rebuild-{int(time.time())}",
            )
            typer.echo(json.dumps(result, indent=2, default=str))

    asyncio.run(command())


@app.command("workbook-dry-run")
def workbook_dry_run(
    workbook: Annotated[Path, typer.Argument(exists=True, readable=True)],
    report_file: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Validate the workbook and persist a hash-bound approval report."""

    async def command() -> None:
        async with get_session_factory()() as session:
            run = await save_dry_run(session, workbook)
            report = json.dumps({"run_id": str(run.id), **run.report}, indent=2, default=str)
            if report_file:
                await asyncio.to_thread(report_file.write_text, report + "\n", encoding="utf-8")
            typer.echo(report)

    asyncio.run(command())


@app.command("workbook-commit")
def workbook_commit(
    run_id: Annotated[UUID, typer.Option(help="Validated dry-run ID")],
    workbook: Annotated[Path, typer.Argument(exists=True, readable=True)],
    approved_by: Annotated[str, typer.Option(help="Administrator username")],
) -> None:
    """Commit the exact workbook approved by a validated dry run."""

    async def command() -> None:
        async with get_session_factory()() as session:
            counts = await commit_approved_run(
                session,
                run_id=run_id,
                workbook_path=workbook,
                administrator_username=approved_by,
            )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(command())
