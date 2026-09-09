"""PostgreSQL-backed Alembic upgrade and metadata-drift tests."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import BigInteger, MetaData, Table, create_engine, inspect, text
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from filament_manager.config import DatabaseConfig, get_settings
from filament_manager.models.enums import PrintJobStatus, ProfileStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplateRevision,
    Spool,
)
from filament_manager.startup import upgrade_database


def insert_legacy_record(session: Session, record: object) -> None:
    """Seed only columns present at the migration under test, with mapped defaults.

    Current ORM INSERTs include newer columns and cannot seed an older schema.
    Keep the real historical schema intact instead of adding test-only columns.
    """
    mapped = record.__table__
    table = Table(mapped.name, MetaData(), autoload_with=session.connection())
    for column in table.columns:
        if column.name in mapped.c:
            column.default = mapped.c[column.name].default
            column.type = mapped.c[column.name].type
    values = {
        column.name: getattr(record, column.name)
        for column in table.columns
        if getattr(record, column.name, None) is not None
    }
    record.id = session.scalar(table.insert().values(**values).returning(table.c.id))


@pytest.mark.integration
@pytest.mark.parametrize("collision", [False, True])
def test_unknown_manufacturer_upgrade_preserves_archived_filaments_and_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    collision: bool,
) -> None:
    """Consolidate only placeholder brands, retaining physical and historical identity evidence."""

    from filament_manager.models.inventory import Printer, Vendor
    from filament_manager.models.printing import PrintJob

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", url)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "b6c7d8e9f012")
        engine = create_engine(url)
        with Session(engine) as session:
            old, known = Vendor(name="Unspecified manufacturer"), Vendor(name="Maker")
            session.add_all([old, known])
            session.flush()
            products = [
                FilamentProduct(
                    vendor_id=vendor_id,
                    product_name="Duplicate" if collision else f"Legacy {index}",
                    material_type="PLA",
                    color_name="Black",
                    color_hex="000000",
                    diameter_mm=Decimal("1.75000"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                    archived=True,
                )
                for index, vendor_id in enumerate((old.id, None, known.id))
            ]
            session.add_all(products)
            printer = Printer(
                printer_code="test",
                name="Test",
                moonraker_base_url="http://test.invalid",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            insert_legacy_record(session, printer)
            session.flush()
            snapshot = {"vendor_name": "Unspecified manufacturer", "filament_diameter_mm": "1.75000"}
            spools = [
                Spool(
                    spool_code=f"spool-{index}",
                    filament_product_id=product.id,
                    nominal_net_mass_g=Decimal("1000"),
                    tare_mass_g=Decimal("200"),
                    remaining_mass_expected_g=Decimal("500"),
                    remaining_mass_effective_g=Decimal("500"),
                )
                for index, product in enumerate(products)
            ]
            for spool in spools:
                insert_legacy_record(session, spool)
            session.flush()
            jobs = [
                PrintJob(
                    printer_id=printer.id,
                    spool_id=spool.id,
                    filament_product_id=spool.filament_product_id,
                    filename="old.gcode",
                    status=PrintJobStatus.COMPLETED,
                    print_settings_snapshot=snapshot,
                )
                for spool in spools
            ]
            session.add_all(jobs)
            session.commit()
            ids, known_id = [p.id for p in products], known.id
            links = [
                (job.id, spool.id, spool.filament_product_id) for job, spool in zip(jobs, spools, strict=True)
            ]
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            with pytest.raises(Exception, match="Spool codes are immutable"):
                connection.execute(
                    text("UPDATE spools SET spool_code = 'RENAMED' WHERE id = :id"), {"id": links[0][1]}
                )
            connection.rollback()
        if collision:
            with pytest.raises(RuntimeError, match="legacy filament identity rule"):
                command.downgrade(config, "b6c7d8e9f012")
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "fa012b3c4d56"
        else:
            command.downgrade(config, "b6c7d8e9f012")
            assert "uq_filament_product_identity" in {
                item["name"] for item in inspect(engine).get_unique_constraints("filament_products")
            }
            command.upgrade(config, "head")
        with Session(engine) as session:
            unknown_id = session.scalar(sa_select(Vendor.id).where(Vendor.name == "Unknown"))
            assert unknown_id is not None
            assert [session.get(FilamentProduct, identifier).vendor_id for identifier in ids] == [
                unknown_id,
                unknown_id,
                known_id,
            ]
            for job_id, spool_id, product_id in links:
                job = session.get(PrintJob, job_id)
                spool = session.get(Spool, spool_id)
                assert job.print_settings_snapshot == snapshot
                assert (job.spool_id, job.filament_product_id) == (spool_id, product_id)
                assert spool.filament_product_id == product_id
                assert spool.tare_mass_g == Decimal("200")
                assert spool.remaining_mass_effective_g == Decimal("500")
                product = session.get(FilamentProduct, product_id)
                assert product.archived
                expected_name = "Duplicate" if collision else f"Legacy {ids.index(product_id)}"
                assert product.product_name == expected_name
            assert (
                session.scalar(sa_select(Vendor.id).where(Vendor.name == "Unspecified manufacturer")) is None
            )
        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_plate_cleaning_removal_preserves_mesh_and_selection_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-trip the prior schema with real cleaning, mesh, and selection records."""

    from filament_manager.models.enums import NotificationSeverity
    from filament_manager.models.inventory import BuildPlate, BuildPlateSurface, Printer
    from filament_manager.models.operations import AuditEvent, Notification

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", url)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(url)
        at = datetime(2026, 8, 1, tzinfo=UTC)
        with Session(engine) as session:
            plate = BuildPlate(plate_code="P1", display_name="Retained plate")
            session.add(plate)
            session.flush()
            side = BuildPlateSurface(
                build_plate_id=plate.id,
                side="a",
                surface_code="P1",
                klipper_mesh_profile="P1",
                last_mesh_calibrated_at=at,
            )
            session.add(side)
            session.flush()
            printer = Printer(
                printer_code="test",
                name="Test",
                moonraker_base_url="http://test.invalid",
                nozzle_diameter_mm=Decimal("0.4"),
                active_plate_id=plate.id,
                active_plate_surface_id=side.id,
            )
            session.add(printer)
            plate_id, side_id = plate.id, side.id
            for suffix in ("cleaning-due", "mesh-due"):
                session.add(
                    Notification(
                        deduplication_key=f"plate:{plate_id}:{suffix}",
                        category="plate_maintenance_due",
                        severity=NotificationSeverity.WARNING,
                        title=suffix,
                        message=suffix,
                        created_at=at,
                        last_seen_at=at,
                    )
                )
            for action, after in (
                (
                    "build_plate.select",
                    {"active_plate_id": str(plate_id), "active_plate_surface_id": str(side_id)},
                ),
                ("build_plate.maintenance", {"maintenance_type": "cleaned"}),
                ("build_plate.maintenance", {"cleaned": True, "mesh_calibrated": True}),
            ):
                session.add(
                    AuditEvent(
                        source="web",
                        action=action,
                        object_type="build_plate",
                        object_id=plate_id,
                        before=None,
                        after=after,
                        correlation_id="migration-test",
                        occurred_at=at,
                    )
                )
            session.commit()
        command.downgrade(config, "f4a5b6c7d890")
        with engine.begin() as connection:
            for event_type in ("CLEANED", "MESH_CALIBRATED"):
                connection.execute(
                    text("""INSERT INTO build_plate_maintenance_events
                    (id, build_plate_id, build_plate_surface_id, maintenance_type,
                     source, occurred_at, created_at)
                    VALUES (:id, :plate, :side, :kind, 'web', :at, :at)"""),
                    {"id": uuid4(), "plate": plate_id, "side": side_id, "kind": event_type, "at": at},
                )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM build_plate_maintenance_events")) == 1
            assert connection.scalar(text("SELECT count(*) FROM notifications")) == 1
            assert connection.scalar(text("SELECT title FROM notifications")) == "mesh-due"
            assert connection.scalar(text("SELECT count(*) FROM audit_events")) == 2
            assert connection.scalar(text("SELECT last_activated_at FROM build_plates")) == at
            assert connection.scalar(text("SELECT last_activated_at FROM build_plate_surfaces")) == at
            assert connection.scalar(text("SELECT last_mesh_calibrated_at FROM build_plate_surfaces")) == at
            assert connection.scalar(text("SELECT plate_selection_initialized FROM printers")) is True
        assert "last_cleaned_at" not in {
            column["name"] for column in inspect(engine).get_columns("build_plates")
        }
        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_choice_cleanup_retains_archived_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upgrade 0.7.1 choices, correct None finishes, and never resurrect orphan names."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", url)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "e3f4a5b6c789")
        engine = create_engine(url)
        from filament_manager.models.inventory import FilamentAttributeChoice, FilamentColor

        with Session(engine) as session:
            product = FilamentProduct(
                material_type="PLA",
                color_name="Copper",
                archived=True,
                filler="Glass",
                finish=" nOnE ",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add(product)
            for name in ("Copper", "Orphan"):
                session.add(
                    FilamentColor(
                        name=name,
                        normalized_name=name.casefold(),
                        color_hex="AA6633",
                        color_mode="solid",
                        color_hexes=["AA6633"],
                    )
                )
            for index, (kind, name) in enumerate(
                [
                    ("filler", "Glass"),
                    ("filler", "Unused"),
                    ("finish", "None"),
                    ("finish", "Silk"),
                ]
            ):
                session.add(FilamentAttributeChoice(kind=kind, name=name, name_key=str(index)))
            session.commit()
            product_id = product.id
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT filler, finish, archived, record_version FROM filament_products WHERE id=:id"),
                {"id": product_id},
            ).one()
            assert tuple(row) == ("Glass", "Standard", True, 3)
            assert set(connection.scalars(text("SELECT name FROM filament_colors"))) == {"Copper"}
            assert set(connection.execute(text("SELECT kind, name FROM filament_attribute_choices"))) == {
                ("filler", "Glass"),
                ("finish", "Standard"),
            }
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM audit_events WHERE action='filament.choice_normalization'")
                )
                == 1
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM outbox_jobs WHERE idempotency_key LIKE 'choice-normalization:%'"
                    )
                )
                == 1
            )
        command.downgrade(config, "e3f4a5b6c789")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert set(connection.scalars(text("SELECT name FROM filament_colors"))) == {"Copper"}
            assert (
                connection.scalar(
                    text("SELECT record_version FROM filament_products WHERE id=:id"), {"id": product_id}
                )
                == 3
            )
        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_modifier_catalog_backfills_only_blanks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upgrade populated 0.7.0 data and retain explicit modifier labels unchanged."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", url)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "b0c1d2e3f456")
        engine = create_engine(url)
        with Session(engine) as session:
            products = [
                FilamentProduct(
                    material_type="PLA",
                    color_name=color,
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                )
                for color in ("Blue", "Red")
            ]
            session.add_all(products)
            session.flush()
            blank_id, populated_id = (product.id for product in products)
            labels = ["Bucket %_12", "Bucket %_12", "bucket %_12", "Archived shelf", None]
            for index, label in enumerate(labels):
                insert_legacy_record(
                    session,
                    Spool(
                        spool_code=f"MIGRATION-{index}",
                        filament_product_id=blank_id,
                        nominal_net_mass_g=Decimal("1000"),
                        tare_mass_g=Decimal("200"),
                        remaining_mass_expected_g=Decimal("800"),
                        remaining_mass_effective_g=Decimal("800"),
                        location=label,
                        archived=index == 3,
                    ),
                )
            session.execute(
                text("UPDATE filament_products SET filler = NULL, finish = :blank WHERE id = :id"),
                {"blank": " \t\n", "id": blank_id},
            )
            session.execute(
                text(
                    "UPDATE filament_products SET filler = 'Carbon Fiber', finish = 'Matte', "
                    "archived = true WHERE id = :id"
                ),
                {"id": populated_id},
            )
            session.commit()
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert set(connection.scalars(text("SELECT name FROM spool_location_choices"))) == {
                "Bucket %_12",
                "bucket %_12",
                "Archived shelf",
            }
            assert list(connection.scalars(text("SELECT location FROM spools ORDER BY spool_code"))) == labels
            rows = {
                row.id: row
                for row in connection.execute(
                    text("SELECT id, filler, finish, record_version FROM filament_products")
                )
            }
            assert (rows[blank_id].filler, rows[blank_id].finish, rows[blank_id].record_version) == (
                "None",
                "Standard",
                3,
            )
            assert (
                rows[populated_id].filler,
                rows[populated_id].finish,
                rows[populated_id].record_version,
            ) == ("Carbon Fiber", "Matte", 2)
            assert set(connection.execute(text("SELECT kind, name FROM filament_attribute_choices"))) == {
                ("filler", "None"),
                ("finish", "Standard"),
                ("filler", "Carbon Fiber"),
                ("finish", "Matte"),
            }
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM audit_events WHERE action = 'filament.modifier_defaults'")
                )
                == 1
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM outbox_jobs WHERE idempotency_key LIKE 'modifier-defaults:%'")
                )
                == 1
            )
        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_template_only_settings_migration_appends_corrected_profile_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace legacy template-only settings while preserving profile pressure advance."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", database_url)
        get_settings.cache_clear()
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, "c5d6e7f8a901")
        engine = create_engine(database_url)

        with Session(engine) as session:
            # Seed the historical schema without today's additional ORM columns.
            printer_id = uuid4()
            session.execute(
                text("""INSERT INTO printers
                (id, printer_code, name, moonraker_base_url, nozzle_diameter_mm,
                 build_volume, status, spool_preflight_status, record_version)
                VALUES (:id, 'migration-printer', 'Migration Printer',
                        'http://moonraker.invalid', 0.4, '{}', 'unknown', 'unknown', 1)"""),
                {"id": printer_id},
            )
            nozzle_id = uuid4()
            template_id = uuid4()
            session.execute(
                text(
                    """
                    INSERT INTO nozzles (
                        id, nozzle_code, diameter_mm, material, status, record_version,
                        created_at, updated_at
                    ) VALUES (
                        :id, 'NZ-040', 0.4, 'Brass', 'AVAILABLE', 1,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": nozzle_id},
            )
            session.execute(
                text(
                    """
                    INSERT INTO material_templates (
                        id, name, material_type, printer_id, nozzle_diameter_mm,
                        filament_diameter_mm, active, record_version, created_at, updated_at
                    ) VALUES (
                        :id, 'Template PLA', 'PLA', :printer_id, 0.4,
                        1.75, true, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": template_id, "printer_id": printer_id},
            )
            revision = MaterialTemplateRevision(
                material_template_id=template_id,
                version=1,
                status=ProfileStatus.PUBLISHED,
                settings={
                    "extruder_temp_c": "210",
                    "bed_temp_c": "60",
                    "flow_percent": "100",
                    "cooling_enabled": True,
                    "cooling_min_percent": "20",
                    "cooling_max_percent": "100",
                    "pressure_advance": "0.04",
                    "filament_density_g_cm3": "1.24",
                    "cura_extensions": {
                        "retraction_enable": True,
                        "acceleration_print": "5000",
                        "acceleration_travel": "7000",
                        "klipper_smooth_time_factor": "0.04",
                    },
                },
            )
            session.add(revision)
            session.flush()
            product = FilamentProduct(
                material_type="PLA",
                color_name="Blue",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
                source_template_revision_id=revision.id,
            )
            session.add(product)
            session.flush()
            # Seed through the historical schema rather than today's ORM. The
            # current mapping intentionally contains columns that do not exist
            # until later revisions, including ``initial_bed_temp_c``.
            setting_overrides = {
                "extruder_temp_c": "215",
                "pressure_advance": "0.09",
                "cura_extensions": {
                    "retraction_enable": False,
                    "acceleration_print": "9000",
                    "acceleration_travel": "10000",
                    "klipper_smooth_time_factor": "0.08",
                },
            }
            cura_extensions = {
                "retraction_enable": False,
                "acceleration_print": "9000",
                "acceleration_travel": "10000",
                "klipper_smooth_time_factor": "0.08",
            }
            session.execute(
                text(
                    """
                    INSERT INTO material_profiles (
                        id, filament_product_id, printer_id, nozzle_diameter_mm,
                        version, status, extruder_temp_c, bed_temp_c, flow_percent,
                        cooling_enabled, cooling_min_percent, cooling_max_percent,
                        pressure_advance, filament_density_g_cm3,
                        source_template_revision_id, setting_overrides,
                        cura_extensions_schema_version, cura_extensions, record_version
                    ) VALUES (
                        :id, :filament_product_id, :printer_id, :nozzle_diameter_mm,
                        1, CAST('PUBLISHED' AS profile_status), :extruder_temp_c,
                        :bed_temp_c, :flow_percent, true, :cooling_min_percent,
                        :cooling_max_percent, :pressure_advance,
                        :filament_density_g_cm3, :source_template_revision_id,
                        CAST(:setting_overrides AS jsonb), 1,
                        CAST(:cura_extensions AS jsonb), 1
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "filament_product_id": product.id,
                    "printer_id": printer_id,
                    "nozzle_diameter_mm": Decimal("0.4"),
                    "extruder_temp_c": Decimal("215"),
                    "bed_temp_c": Decimal("60"),
                    "flow_percent": Decimal("100"),
                    "cooling_min_percent": Decimal("20"),
                    "cooling_max_percent": Decimal("100"),
                    "pressure_advance": Decimal("0.09"),
                    "filament_density_g_cm3": Decimal("1.24"),
                    "source_template_revision_id": revision.id,
                    "setting_overrides": json.dumps(setting_overrides),
                    "cura_extensions": json.dumps(cura_extensions),
                },
            )
            session.commit()
            product_id = product.id

        command.upgrade(alembic_config, "head")
        with Session(engine) as session:
            profiles = list(
                session.query(MaterialProfile)
                .filter(MaterialProfile.filament_product_id == product_id)
                .order_by(MaterialProfile.version)
            )
            assert len(profiles) == 2
            migrated = profiles[-1]
            assert migrated.version == 2
            assert migrated.extruder_temp_c == Decimal("215")
            assert migrated.pressure_advance == Decimal("0.09")
            assert migrated.cura_extensions == {
                "retraction_enable": False,
                "acceleration_print": "5000",
                "acceleration_travel": "7000",
                "klipper_smooth_time_factor": "0.04",
            }
            assert migrated.setting_overrides == {
                "extruder_temp_c": "215",
                "pressure_advance": "0.09",
                "cura_extensions": {"retraction_enable": False},
            }
            assert migrated.checksum is not None and len(migrated.checksum) == 64
            assert (
                session.execute(
                    text(
                        "SELECT count(*) FROM outbox_jobs "
                        "WHERE job_type = 'google.profile.publish' "
                        "AND payload->>'profile_id' = :profile_id"
                    ),
                    {"profile_id": str(migrated.id)},
                ).scalar_one()
                == 1
            )

        engine.dispose()
        get_settings.cache_clear()


@pytest.mark.integration
def test_previous_schema_automatically_upgrades_to_metadata_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Upgrade an existing 0.1.2 schema and prove models need no further changes."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", database_url)
        get_settings.cache_clear()
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, "8c3a0f1e7d92")

        engine = create_engine(database_url)
        assert "material_templates" not in inspect(engine).get_table_names()
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO outbox_jobs (
                        id, job_type, idempotency_key, aggregate_type,
                        aggregate_id, aggregate_version, payload, status,
                        attempts, max_attempts, next_attempt_at, created_at
                    ) VALUES (
                        '10000000-0000-0000-0000-000000000001',
                        'spoolman.spool.upsert', 'migration-recovery-test', 'spool',
                        '20000000-0000-0000-0000-000000000002', 1,
                        '{}'::jsonb, 'DEAD'::job_status, 12, 12,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        command.upgrade(alembic_config, "f2a3b4c5d678")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO outbox_jobs (
                        id, job_type, idempotency_key, aggregate_type,
                        aggregate_id, aggregate_version, payload, status,
                        attempts, max_attempts, next_attempt_at, created_at
                    ) VALUES (
                        '10000000-0000-0000-0000-000000000003',
                        'moonraker.state.reconcile',
                        'periodic:moonraker.state.reconcile:123', 'system',
                        '20000000-0000-0000-0000-000000000004', 123,
                        '{}'::jsonb, 'DEAD'::job_status, 12, 12,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        command.upgrade(alembic_config, "a3b4c5d6e789")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO outbox_jobs (
                        id, job_type, idempotency_key, aggregate_type,
                        aggregate_id, aggregate_version, payload, status,
                        attempts, max_attempts, next_attempt_at, created_at,
                        last_error_class, last_error_message
                    ) VALUES
                    (
                        '10000000-0000-0000-0000-000000000005',
                        'moonraker.state.reconcile',
                        'periodic:moonraker.state.reconcile:456', 'system',
                        '20000000-0000-0000-0000-000000000004', 456,
                        '{}'::jsonb, 'DEAD'::job_status, 12, 12,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                        'RuntimeError', 'bounded Moonraker failure'
                    ),
                    (
                        '10000000-0000-0000-0000-000000000006',
                        'spoolman.filament.upsert',
                        'filament:migration:v1', 'filament_product',
                        '20000000-0000-0000-0000-000000000006', 1,
                        '{}'::jsonb, 'DEAD'::job_status, 12, 12,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                        'SpoolmanError', 'Spoolman POST /filament failed'
                    ),
                    (
                        '10000000-0000-0000-0000-000000000007',
                        'spoolman.spool.adjust_weight',
                        'spool:migration:weight:v1', 'spool',
                        '20000000-0000-0000-0000-000000000007', 1,
                        '{}'::jsonb, 'DEAD'::job_status, 12, 12,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                        'SpoolmanError', 'Spoolman PUT /spool/7/measure failed'
                    ),
                    (
                        '10000000-0000-0000-0000-000000000008',
                        'spoolman.spool.adjust_weight',
                        'spool:migration:weight:v2', 'spool',
                        '20000000-0000-0000-0000-000000000007', 2,
                        '{}'::jsonb, 'PENDING'::job_status, 4, 12,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '1 second',
                        'SpoolmanError', 'Spoolman PUT /spool/7/measure failed'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO outbox_jobs (
                        id, job_type, idempotency_key, aggregate_type,
                        aggregate_id, aggregate_version, payload, status,
                        attempts, max_attempts, next_attempt_at, created_at,
                        completed_at
                    ) VALUES (
                        '10000000-0000-0000-0000-000000000009',
                        'moonraker.state.reconcile',
                        'periodic:moonraker.state.reconcile:recovered', 'system',
                        '20000000-0000-0000-0000-000000000004', 457,
                        '{}'::jsonb, 'COMPLETED'::job_status, 0, 12,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '2 seconds',
                        CURRENT_TIMESTAMP + INTERVAL '2 seconds'
                    )
                    """
                )
            )

        upgrade_database(DatabaseConfig(url=database_url))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "fa012b3c4d56"
            assert (
                connection.scalar(
                    text(
                        """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_name = 'material_profiles'
                      AND column_name = 'ironing_enabled'
                    """
                    )
                )
                == 0
            )
            assert (
                connection.scalar(
                    text(
                        """
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'nozzles'
                      AND column_name = 'printer_id'
                    """
                    )
                )
                == "NO"
            )
            assert (
                connection.scalar(
                    text(
                        """
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'material_templates'
                      AND column_name = 'nozzle_id'
                    """
                    )
                )
                == "NO"
            )
            assert (
                connection.scalar(
                    text(
                        """
                    SELECT count(*)
                    FROM pg_indexes
                    WHERE tablename = 'nozzles'
                      AND indexname = 'uq_nozzles_printer_code'
                    """
                    )
                )
                == 1
            )
            assert (
                connection.scalar(
                    text(
                        """
                    SELECT count(*)
                    FROM pg_indexes
                    WHERE tablename = 'material_templates'
                      AND indexname = 'uq_material_template_active_nozzle_scope'
                    """
                    )
                )
                == 1
            )
            recovered = connection.execute(
                text(
                    """
                    SELECT status::text, attempts
                    FROM outbox_jobs
                    WHERE id = '10000000-0000-0000-0000-000000000001'
                    """
                )
            ).one()
            assert recovered == ("PENDING", 0)
            periodic_status = connection.scalar(
                text(
                    """
                    SELECT status::text FROM outbox_jobs
                    WHERE id = '10000000-0000-0000-0000-000000000003'
                    """
                )
            )
            assert periodic_status == "SUPERSEDED"
            assert (
                connection.scalar(
                    text(
                        "SELECT status::text FROM outbox_jobs "
                        "WHERE id = '10000000-0000-0000-0000-000000000005'"
                    )
                )
                == "SUPERSEDED"
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT status::text FROM outbox_jobs "
                        "WHERE id = '10000000-0000-0000-0000-000000000006'"
                    )
                )
                == "SUPERSEDED"
            )
            recovered_weight = connection.execute(
                text(
                    "SELECT status::text, attempts, last_error_at IS NOT NULL "
                    "FROM outbox_jobs "
                    "WHERE id = '10000000-0000-0000-0000-000000000008'"
                )
            ).one()
            assert recovered_weight == ("PENDING", 0, False)
            assert (
                connection.scalar(
                    text(
                        "SELECT status::text FROM outbox_jobs "
                        "WHERE id = '10000000-0000-0000-0000-000000000007'"
                    )
                )
                == "SUPERSEDED"
            )
        inspector = inspect(engine)
        assert "material_templates" in inspector.get_table_names()
        assert "material_template_revisions" in inspector.get_table_names()
        assert {"source_workstation_agent_id", "source_cura_material_id"} <= {
            column["name"] for column in inspector.get_columns("material_templates")
        }
        profile_columns = {column["name"]: column for column in inspector.get_columns("material_profiles")}
        assert "setting_overrides" in profile_columns
        assert "retraction_prime_speed_mm_s" in profile_columns
        assert profile_columns["source_template_revision_id"]["nullable"] is False
        assert "cura_managed_edit_receipts" in inspector.get_table_names()
        assert "cura_takeover_mappings" in inspector.get_table_names()
        assert "print_jobs" in inspector.get_table_names()
        assert "print_material_segments" in inspector.get_table_names()
        assert "print_assessments" in inspector.get_table_names()
        assert "notifications" in inspector.get_table_names()
        assert "build_plate_maintenance_events" in inspector.get_table_names()
        assert "cura_management_enabled" in {
            column["name"] for column in inspector.get_columns("workstation_agents")
        }
        assert "location_authoritative" in {column["name"] for column in inspector.get_columns("spools")}
        assert "filament_colors" in inspector.get_table_names()
        assert "last_info_sync_at" in {column["name"] for column in inspector.get_columns("printers")}
        assert "product_name" in {column["name"] for column in inspector.get_columns("build_plates")}
        assert "nozzles" in inspector.get_table_names()
        assert "nozzle_lifecycle_events" in inspector.get_table_names()
        assert "diagnostic_runs" in inspector.get_table_names()
        assert "worker_heartbeats" in inspector.get_table_names()
        assert "cura_recovery_snapshots" in inspector.get_table_names()
        assert "cura_recovery_restores" in inspector.get_table_names()
        assert {"image_data", "image_media_type", "image_sha256", "image_version"} <= {
            column["name"] for column in inspector.get_columns("build_plates")
        }
        assert {
            "cura_recovery_status",
            "cura_recovery_message",
            "last_recovery_snapshot_at",
            "last_recovery_restore_at",
            "suppressed_recovery_snapshots",
        } <= {column["name"] for column in inspector.get_columns("workstation_agents")}
        assert "active_nozzle_id" in {column["name"] for column in inspector.get_columns("printers")}
        assert {
            "spool_preflight_status",
            "spool_preflight_message",
            "last_spool_preflight_sync_at",
        } <= {column["name"] for column in inspector.get_columns("printers")}
        outbox_columns = {column["name"]: column for column in inspector.get_columns("outbox_jobs")}
        assert "last_error_at" in outbox_columns
        assert isinstance(outbox_columns["aggregate_version"]["type"], BigInteger)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO outbox_jobs (
                        id, job_type, idempotency_key, aggregate_type,
                        aggregate_id, aggregate_version, payload, status,
                        attempts, max_attempts, next_attempt_at, created_at
                    ) VALUES (
                        '10000000-0000-0000-0000-000000000011',
                        'spoolman.reconcile.full', 'bigint-system-job-test', 'system',
                        '20000000-0000-0000-0000-000000000011', 1700000000000000,
                        '{}'::jsonb, 'PENDING'::job_status, 0, 12,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT aggregate_version FROM outbox_jobs "
                        "WHERE id = '10000000-0000-0000-0000-000000000011'"
                    )
                )
                == 1_700_000_000_000_000
            )
            # Keep the existing downgrade compatibility test meaningful: old
            # schemas cannot represent this intentionally oversized value.
            connection.execute(
                text("DELETE FROM outbox_jobs WHERE id = '10000000-0000-0000-0000-000000000011'")
            )
        assert "nozzle_id" in {column["name"] for column in inspector.get_columns("print_jobs")}
        assert "initial_bed_temp_c" in profile_columns
        assert {
            "initial_bed_temp_c",
            "thumbnail_data",
            "thumbnail_media_type",
            "thumbnail_sha256",
            "thumbnail_width",
            "thumbnail_height",
            "thumbnail_checked_at",
            "print_settings_snapshot",
        } <= {column["name"] for column in inspector.get_columns("print_jobs")}
        assert {
            "capture_request_id",
            "capture_kind",
            "name",
            "description",
            "record_version",
        } <= {column["name"] for column in inspector.get_columns("cura_recovery_snapshots")}
        assert {"source_workstation_agent_id", "source_cura_material_id"} <= set(profile_columns)
        command.check(alembic_config)
        command.downgrade(alembic_config, "a7b8c9d0e123")
        downgraded = inspect(engine)
        assert "print_jobs" not in downgraded.get_table_names()
        assert "notifications" not in downgraded.get_table_names()
        assert "must_change_password" not in {column["name"] for column in downgraded.get_columns("users")}
        command.upgrade(alembic_config, "head")
        command.check(alembic_config)
        engine.dispose()
        get_settings.cache_clear()
