"""PostgreSQL-backed Alembic upgrade and metadata-drift tests."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from testcontainers.community.postgres import PostgresContainer

from filament_manager.config import DatabaseConfig, get_settings
from filament_manager.startup import upgrade_database


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
                    )
                    """
                )
            )

        upgrade_database(DatabaseConfig(url=database_url))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "b4c5d6e7f890"
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
                    "WHERE id = '10000000-0000-0000-0000-000000000007'"
                )
            ).one()
            assert recovered_weight == ("PENDING", 0, True)
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
        assert "last_error_at" in {column["name"] for column in inspector.get_columns("outbox_jobs")}
        assert "nozzle_id" in {column["name"] for column in inspector.get_columns("print_jobs")}
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
