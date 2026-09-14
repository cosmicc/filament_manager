"""Populated whole-plate upgrade preserves history and explicitly resets conflicts."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from filament_manager.config import get_settings
from filament_manager.models.inventory import BuildPlate, BuildPlateSurface
from filament_manager.models.operations import ApplicationSetting, AuditEvent


@pytest.mark.integration
def test_whole_plate_upgrade_and_guarded_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conflicting zero/five becomes unrated by user choice, not silently safe-rated."""
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", postgres.get_connection_url())
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "fa012b3c4d56")
        engine = create_engine(postgres.get_connection_url())
        with Session(engine) as session:
            plates = [
                BuildPlate(plate_code=f"P{index}", display_name=f"Plate {index}") for index in range(1, 5)
            ]
            session.add_all(plates)
            session.flush()
            legacy = {}
            for index, plate in enumerate(plates):
                for side_name, stars in zip(("a", "b"), ((0, 5), (4, 4), (0, 0), (2,))[index], strict=False):
                    code = plate.plate_code + ("b" if side_name == "b" else "")
                    side = BuildPlateSurface(
                        build_plate_id=plate.id, side=side_name, surface_code=code, klipper_mesh_profile=code
                    )
                    session.add(side)
                    session.flush()
                    legacy[str(side.id)] = stars
            template_id = uuid4()
            session.add(
                ApplicationSetting(key=f"plate_ratings.{template_id}", value=legacy, record_version=7)
            )
            session.add(ApplicationSetting(key="private.connection", value={"unchanged": True}))
            ids = [str(plate.id) for plate in plates]
            session.commit()
        command.upgrade(config, "head")
        with Session(engine) as session:
            rating = session.scalar(
                select(ApplicationSetting).where(ApplicationSetting.key == f"plate_ratings.{template_id}")
            )
            assert rating and rating.value == {ids[1]: 4, ids[2]: 0, ids[3]: 2}
            assert rating.record_version == 8
            audit = session.scalar(
                select(AuditEvent).where(AuditEvent.action == "template.plate_ratings.whole_plate")
            )
            assert audit and audit.before == legacy
            assert audit.metadata_json["conflicting_plates_reset"] == [ids[0]]
            session.add(ApplicationSetting(key=f"filament_plate_ratings.{uuid4()}", value={ids[1]: 3}))
            session.commit()
        with pytest.raises(RuntimeError, match="Remove filament build-plate overrides"):
            command.downgrade(config, "fa012b3c4d56")
        with Session(engine) as session:
            custom = session.scalar(
                select(ApplicationSetting).where(ApplicationSetting.key.startswith("filament_plate_ratings."))
            )
            assert custom
            custom.value = {}
            session.commit()
        command.downgrade(config, "fa012b3c4d56")
        command.upgrade(config, "head")
        with Session(engine) as session:
            rating = session.scalar(
                select(ApplicationSetting).where(ApplicationSetting.key == f"plate_ratings.{template_id}")
            )
            assert rating and rating.value == {ids[1]: 4, ids[2]: 0, ids[3]: 2}
            private = session.scalar(
                select(ApplicationSetting).where(ApplicationSetting.key == "private.connection")
            )
            assert private and private.value == {"unchanged": True}
        engine.dispose()
        get_settings.cache_clear()
