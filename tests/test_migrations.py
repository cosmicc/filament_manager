"""PostgreSQL-backed Alembic upgrade and metadata-drift tests."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import BigInteger, create_engine, inspect, text
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from filament_manager.config import DatabaseConfig, get_settings
from filament_manager.models.enums import ProfileStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplateRevision,
    Printer,
)
from filament_manager.startup import upgrade_database


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
            printer = Printer(
                printer_code="migration-printer",
                name="Migration Printer",
                moonraker_base_url="http://moonraker.invalid",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add(printer)
            session.flush()
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
                {"id": template_id, "printer_id": printer.id},
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
                    "printer_id": printer.id,
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
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "a9b0c1d2e345"
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
