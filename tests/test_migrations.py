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

        upgrade_database(DatabaseConfig(url=database_url))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "c7e4a19d2b63"
        inspector = inspect(engine)
        assert "material_templates" in inspector.get_table_names()
        assert "material_template_revisions" in inspector.get_table_names()
        assert "cura_management_enabled" in {
            column["name"] for column in inspector.get_columns("workstation_agents")
        }
        assert "location_authoritative" in {column["name"] for column in inspector.get_columns("spools")}
        command.check(alembic_config)
        engine.dispose()
        get_settings.cache_clear()
