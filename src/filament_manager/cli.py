"""Administrative first-run, seed, and workbook-import commands."""

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy import func, select

from filament_manager.config import get_settings
from filament_manager.database import get_session_factory
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.security import hash_password, normalize_username
from filament_manager.services.seed import seed_configured_system
from filament_manager.services.workbook_import import commit_approved_run, save_dry_run

app = typer.Typer(no_args_is_help=True, help="Filament Manager administrative commands")


def _resolve_bootstrap_password(password_file: Path | None) -> str:
    """Resolve the first-user password from one explicit credential source."""

    environment_password = os.environ.get("FILAMENT_MANAGER_BOOTSTRAP_ADMIN_PASSWORD")
    if password_file is not None and environment_password:
        raise typer.BadParameter(
            "set only one of --password-file or FILAMENT_MANAGER_BOOTSTRAP_ADMIN_PASSWORD"
        )
    if password_file is not None:
        password = password_file.read_text(encoding="utf-8").rstrip("\r\n")
    elif environment_password:
        password = environment_password
    else:
        raise typer.BadParameter("provide --password-file or FILAMENT_MANAGER_BOOTSTRAP_ADMIN_PASSWORD")
    if not password:
        raise typer.BadParameter("bootstrap password cannot be empty")
    return password


@app.command("bootstrap-admin")
def bootstrap_admin(
    username: Annotated[str, typer.Option()],
    display_name: Annotated[str, typer.Option()],
    password_file: Annotated[Path | None, typer.Option(exists=True, readable=True)] = None,
) -> None:
    """Create the first administrator from an environment value or local file."""

    password = _resolve_bootstrap_password(password_file)

    async def command() -> None:
        async with get_session_factory()() as session:
            if await session.scalar(select(func.count(User.id))):
                raise typer.BadParameter("users already exist; use authenticated user management")
            user = User(
                username=username.strip(),
                normalized_username=normalize_username(username),
                display_name=display_name.strip(),
                password_hash=hash_password(password),
                role=UserRole.ADMINISTRATOR,
            )
            session.add(user)
            await session.commit()
            typer.echo(f"Created administrator {user.username}")

    asyncio.run(command())


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
