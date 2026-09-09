"""Populated 0.8.0 upgrade and real PostgreSQL activity attribution."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from test_migrations import insert_legacy_record
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api.schemas import MaterialSettingsInput
from filament_manager.config import get_settings
from filament_manager.domain.profile_inheritance import profile_columns_from_settings
from filament_manager.models.enums import PrintJobStatus, ProfileStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Nozzle,
    Printer,
    Spool,
)
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.services.material_settings import profile_snapshot_checksum
from filament_manager.services.print_activity import print_activity_dates


@pytest.mark.integration
@pytest.mark.asyncio
async def test_density_upgrade_preserves_history_and_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Current ownership changes while captured profiles and event dates remain exact."""
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", url)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "e9f012a3b4c5")
        engine = create_engine(url)
        now = datetime(2026, 9, 8, tzinfo=UTC)
        with Session(engine) as session:
            printer = Printer(
                printer_code="test",
                name="Test",
                moonraker_base_url="http://printer.invalid",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            insert_legacy_record(session, printer)
            nozzle = Nozzle(
                printer_id=printer.id, nozzle_code="N1", diameter_mm=Decimal("0.4"), material="Brass"
            )
            session.add(nozzle)
            session.flush()
            template = MaterialTemplate(
                name="Template PLA",
                material_type="PLA",
                printer_id=printer.id,
                nozzle_id=nozzle.id,
                nozzle_diameter_mm=Decimal("0.4"),
                filament_diameter_mm=Decimal("1.75"),
            )
            session.add(template)
            session.flush()
            settings = MaterialSettingsInput(
                extruder_temp_c=210,
                bed_temp_c=60,
                initial_bed_temp_c=60,
                flow_percent=100,
                cooling_enabled=True,
                cooling_min_percent=0,
                cooling_max_percent=100,
                filament_density_g_cm3=Decimal("1.23456"),
            ).model_dump(mode="json")
            revision = MaterialTemplateRevision(
                material_template_id=template.id,
                version=1,
                status=ProfileStatus.PUBLISHED,
                settings=settings,
                checksum="a" * 64,
            )
            session.add(revision)
            session.flush()
            product = FilamentProduct(
                material_type="PLA",
                color_name="Blue",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.3"),
                nominal_net_mass_g=1000,
                source_template_revision_id=revision.id,
            )
            session.add(product)
            session.flush()
            old = MaterialProfile(
                **profile_columns_from_settings({**settings, "filament_density_g_cm3": "1.3"}),
                filament_product_id=product.id,
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                version=1,
                status=ProfileStatus.PUBLISHED,
                base_template_revision_id=revision.id,
                setting_overrides={"filament_density_g_cm3": "1.3"},
            )
            session.add(old)
            session.flush()
            spool = Spool(
                spool_code="P1",
                filament_product_id=product.id,
                nominal_net_mass_g=1000,
                tare_mass_g=200,
                remaining_mass_expected_g=1000,
                remaining_mass_effective_g=1000,
            )
            insert_legacy_record(session, spool)
            done = PrintJob(
                printer_id=printer.id,
                nozzle_id=nozzle.id,
                spool_id=spool.id,
                filament_product_id=product.id,
                material_profile_id=old.id,
                filename="done.gcode",
                status=PrintJobStatus.COMPLETED,
                started_at=now,
                profile_snapshot={"filament_density_g_cm3": "1.3"},
            )
            failed = PrintJob(
                printer_id=printer.id,
                nozzle_id=nozzle.id,
                filename="failed.gcode",
                status=PrintJobStatus.FAILED,
                started_at=now + timedelta(hours=1),
            )
            queued = PrintJob(
                printer_id=printer.id,
                spool_id=spool.id,
                filament_product_id=product.id,
                filename="active.gcode",
                status=PrintJobStatus.IN_PROGRESS,
                started_at=now + timedelta(days=1),
            )
            session.add_all([done, failed, queued])
            session.flush()
            segment_time = now + timedelta(hours=2)
            session.add(
                PrintMaterialSegment(
                    print_job_id=failed.id,
                    segment_number=1,
                    spool_id=spool.id,
                    filament_product_id=product.id,
                    source="m600",
                    started_at=segment_time,
                    created_at=segment_time,
                )
            )
            old_id, product_id, spool_id, printer_id = old.id, product.id, spool.id, printer.id
            done_id = done.id
            session.commit()
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as session:
            current = session.scalar(select(MaterialProfile).order_by(MaterialProfile.version.desc()))
            assert current is not None and current.id != old_id
            assert current.filament_density_g_cm3 == Decimal("1.23456")
            assert current.setting_overrides == {}
            assert current.checksum == profile_snapshot_checksum(current)
            assert session.get(MaterialProfile, old_id).filament_density_g_cm3 == Decimal("1.3")
            assert session.get(PrintJob, done_id).profile_snapshot == {"filament_density_g_cm3": "1.3"}
            assert session.get(Spool, spool_id).spool_type == "Unknown"
            assert session.get(FilamentProduct, product_id).density_g_cm3 == Decimal("1.23456")
        async_engine = create_async_engine(url)
        async with async_sessionmaker(async_engine)() as session:
            for kind, identity in (("spool", spool_id), ("filament", product_id)):
                dates = (await print_activity_dates(session, kind))[identity]
                assert dates == {"last_completed_print_at": now, "last_other_print_at": segment_time}
            assert (await print_activity_dates(session, "printer"))[printer_id][
                "last_other_print_at"
            ] == now + timedelta(hours=1)
        await async_engine.dispose()
        engine.dispose()
        get_settings.cache_clear()
