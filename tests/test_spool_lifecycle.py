"""Exhausted spool lifecycle, loaded ownership, and retained archive queries."""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api.routes.inventory import list_spools, update_spool
from filament_manager.api.schemas import SpoolUpdate
from filament_manager.models import Base
from filament_manager.models.enums import SpoolStatus
from filament_manager.models.inventory import FilamentProduct, Printer, Spool
from filament_manager.models.operations import AuditEvent, OutboxJob
from filament_manager.services import spool_lifecycle
from filament_manager.services.moonraker_sync import synchronize_active_spool


@pytest.mark.asyncio
@pytest.mark.parametrize("remaining,loaded", [("1", False), ("0.001", False), ("0", True)])
async def test_archive_preserves_usable_or_loaded_inventory(remaining: str, loaded: bool) -> None:
    """Do not round positive remnants to zero or clear physical ownership."""

    session = Mock()
    spool = Spool(
        archived=False,
        remaining_mass_effective_g=Decimal(remaining),
        active_printer_id=uuid4() if loaded else None,
        status=SpoolStatus.EMPTY,
    )
    assert not await spool_lifecycle.archive_empty_spool(
        session,
        spool,
        source="test",
        correlation_id="test",
    )
    assert not spool.archived
    session.add.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_archive_sweep_unload_and_filtered_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use PostgreSQL to verify persistence, idempotency, and physical unload."""

    # Workstation library deployment is independently tested; this fixture has no agents.
    monkeypatch.setattr(spool_lifecycle, "queue_managed_cura_library", AsyncMock(return_value=0))
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        engine = create_async_engine(postgres.get_connection_url())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            product = FilamentProduct(
                material_type="PLA",
                color_name="Blue",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            printer = Printer(
                name="Printer",
                printer_code="printer",
                moonraker_base_url="http://127.0.0.1:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add_all([product, printer])
            await session.flush()
            spools = [
                Spool(
                    spool_code=f"P{index + 1}",
                    filament_product_id=product.id,
                    nominal_net_mass_g=Decimal("1000"),
                    tare_mass_g=Decimal("200"),
                    remaining_mass_expected_g=Decimal(mass),
                    remaining_mass_effective_g=Decimal(mass),
                    status=SpoolStatus.EMPTY if mass == "0" else SpoolStatus.IN_STOCK,
                    archived=False,
                    record_version=1,
                    active_printer_id=printer.id if index == 1 else None,
                    active_extruder="extruder" if index == 1 else None,
                )
                for index, mass in enumerate(["0", "0", "250"])
            ]
            session.add_all(spools)
            await session.commit()
            await spool_lifecycle.archive_existing_empty_spools(session)
            await session.commit()
            assert spools[0].archived
            assert not spools[1].archived
            assert not spools[2].archived
            version = spools[0].record_version
            await spool_lifecycle.archive_existing_empty_spools(session)
            await session.commit()
            assert spools[0].record_version == version
            await synchronize_active_spool(
                session,
                printer_id=printer.id,
                actor_id=None,
                spoolman_id=None,
                correlation_id="unload-test",
            )
            assert spools[1].archived
            assert spools[1].active_printer_id is None
            assert spools[1].status == SpoolStatus.ARCHIVED
            audit = list(
                await session.scalars(select(AuditEvent).where(AuditEvent.action == "spool.empty.archive"))
            )
            assert len(audit) == 2
            jobs = list(await session.scalars(select(OutboxJob)))
            assert {job.job_type for job in jobs} >= {
                "spoolman.spool.upsert",
                "google.inventory.publish",
                "spoolman.filament.upsert",
            }
            kwargs = {
                "_": Mock(),
                "session": session,
                "material": None,
                "color": None,
                "location_exact": None,
                "limit": 50,
                "offset": 0,
            }
            active = await list_spools(**kwargs)
            archived = await list_spools(**kwargs, archived_only=True)
            all_spools = await list_spools(**kwargs, include_archived=True)
            assert active.total == 1
            assert {item["spool_code"] for item in active.items} == {"P3"}
            assert archived.total == 2
            assert {item["spool_code"] for item in archived.items} == {"P1", "P2"}
            assert all_spools.total == 3
            request = Mock()
            request.state.correlation_id = "archive-correction-test"
            operator = Mock(id=None)
            await update_spool(
                spools[2].id,
                SpoolUpdate(expected_version=spools[2].record_version, remaining_mass_g=Decimal("0")),
                request,
                operator,
                session,
            )
            assert spools[2].archived
            assert spools[2].spool_code == "P3"
            request.state.correlation_id = "archive-positive-correction-test"
            await update_spool(
                spools[2].id,
                SpoolUpdate(expected_version=spools[2].record_version, remaining_mass_g=Decimal("100")),
                request,
                operator,
                session,
            )
            assert spools[2].archived
            assert spools[2].status == SpoolStatus.ARCHIVED
            request.state.correlation_id = "archive-restore-test"
            await update_spool(
                spools[2].id,
                SpoolUpdate(expected_version=spools[2].record_version, archived=False),
                request,
                operator,
                session,
            )
            assert not spools[2].archived
            assert spools[2].remaining_mass_effective_g == Decimal("100")
        await engine.dispose()
