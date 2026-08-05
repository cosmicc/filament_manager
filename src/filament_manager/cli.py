"""Administrative first-run, seed, and workbook-import commands."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy import func, select

from filament_manager.config import get_settings
from filament_manager.database import get_session_factory
from filament_manager.models.auth import User
from filament_manager.models.enums import PlateCondition, PlateStatus, UserRole
from filament_manager.models.inventory import BuildPlate, Printer
from filament_manager.security import hash_password, normalize_username
from filament_manager.services.workbook_import import commit_approved_run, save_dry_run

app = typer.Typer(no_args_is_help=True, help="Filament Manager administrative commands")


@app.command("bootstrap-admin")
def bootstrap_admin(
    username: Annotated[str, typer.Option()],
    display_name: Annotated[str, typer.Option()],
    password_file: Annotated[Path, typer.Option(exists=True, readable=True)],
) -> None:
    """Create the first administrator from a local/Docker secret file."""

    async def command() -> None:
        async with get_session_factory()() as session:
            if await session.scalar(select(func.count(User.id))):
                raise typer.BadParameter("users already exist; use authenticated user management")
            password = (await asyncio.to_thread(password_file.read_text, encoding="utf-8")).rstrip("\r\n")
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
    """Idempotently seed P1-P5 and configured printers."""

    async def command() -> None:
        settings = get_settings()
        async with get_session_factory()() as session:
            for code in settings.plates.allowed_codes:
                if not await session.scalar(select(BuildPlate.id).where(BuildPlate.plate_code == code)):
                    session.add(
                        BuildPlate(
                            plate_code=code,
                            display_name=f"Build Plate {code}",
                            klipper_mesh_profile=code,
                            condition=PlateCondition.GOOD,
                            status=PlateStatus.ACTIVE,
                        )
                    )
            for configured in settings.moonraker.printers:
                if not await session.scalar(select(Printer.id).where(Printer.printer_code == configured.id)):
                    session.add(
                        Printer(
                            printer_code=configured.id,
                            name=configured.name,
                            moonraker_base_url=str(configured.base_url),
                            nozzle_diameter_mm=Decimal(str(configured.nozzle_diameter_mm)),
                        )
                    )
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
