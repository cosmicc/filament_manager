"""PostgreSQL-backed build-plate synchronization tests."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.clients.moonraker import MoonrakerBedMeshState
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import PlateCondition, PlateStatus, PlateSurfaceTexture, UserRole
from filament_manager.models.inventory import BuildPlate, BuildPlateSurface, Printer
from filament_manager.models.operations import AuditEvent, OutboxJob
from filament_manager.security import hash_password
from filament_manager.services import events
from filament_manager.services.build_plate_sync import synchronize_build_plates


def _settings(database_url: str) -> Settings:
    """Create complete connector settings for a disposable PostgreSQL test."""

    return Settings.model_validate(
        {
            "app": {
                "base_url": "http://testserver",
                "allowed_hosts": ["testserver"],
                "secure_cookies": False,
            },
            "database": {"url": database_url},
            "spoolman": {"base_url": "http://spoolman.test:8000"},
            "moonraker": {
                "printers": [
                    {
                        "id": "test-printer",
                        "name": "Test Printer",
                        "base_url": "http://moonraker.test:7125",
                        "websocket_url": "ws://moonraker.test:7125/websocket",
                        "nozzle_diameter_mm": 0.4,
                    }
                ]
            },
            "google": {"enabled": False},
            "sync": {},
            "plates": {"allowed_codes": ["P1", "P2", "P3", "P4", "P5"]},
            "devices": {},
            "security": {},
        }
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_creates_preserves_marks_missing_and_tracks_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One transaction imports meshes, preserves metadata, and aligns printer state."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = _settings(database_url)
        monkeypatch.setattr(events, "get_settings", lambda: settings)
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            administrator = User(
                username="plate-admin",
                normalized_username="plate-admin",
                display_name="Plate Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            p1 = BuildPlate(
                plate_code="P1",
                display_name="Textured PEI",
                condition=PlateCondition.WORN,
                status=PlateStatus.ACTIVE,
                notes="Preserve this metadata",
            )
            p3 = BuildPlate(
                plate_code="P3",
                display_name="Build Plate P3",
                condition=PlateCondition.GOOD,
                status=PlateStatus.ACTIVE,
            )
            printer = Printer(
                printer_code="test-printer",
                name="Test Printer",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add_all([administrator, p1, p3, printer])
            await session.flush()
            p1_side_a = BuildPlateSurface(
                build_plate_id=p1.id,
                side="a",
                surface_code="P1",
                klipper_mesh_profile="P1",
                surface_material="PEI",
                texture=PlateSurfaceTexture.TEXTURED,
            )
            p3_side_a = BuildPlateSurface(
                build_plate_id=p3.id,
                side="a",
                surface_code="P3",
                klipper_mesh_profile="P3",
            )
            session.add_all([p1_side_a, p3_side_a])
            await session.commit()

            first = await synchronize_build_plates(
                session,
                printer_id=printer.id,
                mesh_state=MoonrakerBedMeshState(
                    profile_names=("default", "P1", "P2", "P10b", "P01"),
                    active_profile="P10b",
                ),
                actor_id=administrator.id,
                correlation_id="plate-sync-1",
            )

            assert first.discovered_codes == ("P1", "P2", "P10b")
            assert first.created_codes == ("P2", "P10b")
            assert first.unavailable_codes == ("P3",)
            assert first.ignored_profile_count == 2
            assert first.active_plate_code == "P10"
            assert first.active_surface_code == "P10b"
            assert first.active_plate_changed is True

            stored_p1 = await session.scalar(select(BuildPlate).where(BuildPlate.plate_code == "P1"))
            stored_printer = await session.get(Printer, printer.id)
            assert stored_p1 is not None
            assert stored_p1.display_name == "Textured PEI"
            assert stored_p1.condition == PlateCondition.WORN
            assert stored_p1.notes == "Preserve this metadata"
            stored_p1_surface = await session.scalar(
                select(BuildPlateSurface).where(BuildPlateSurface.surface_code == "P1")
            )
            stored_p3_surface = await session.scalar(
                select(BuildPlateSurface).where(BuildPlateSurface.surface_code == "P3")
            )
            assert stored_p1_surface is not None
            assert stored_p1_surface.surface_material == "PEI"
            assert stored_p1_surface.texture == PlateSurfaceTexture.TEXTURED
            assert stored_p1_surface.mesh_available is True
            assert stored_p3_surface is not None and stored_p3_surface.mesh_available is False
            assert stored_printer is not None and stored_printer.active_plate_id is not None
            active_plate = await session.get(BuildPlate, stored_printer.active_plate_id)
            assert active_plate is not None and active_plate.plate_code == "P10"
            active_surface = await session.get(BuildPlateSurface, stored_printer.active_plate_surface_id)
            assert active_surface is not None and active_surface.surface_code == "P10b"
            assert await session.scalar(select(func.count(OutboxJob.id))) == 2

            second = await synchronize_build_plates(
                session,
                printer_id=printer.id,
                mesh_state=MoonrakerBedMeshState(
                    profile_names=("P1", "P2", "P10b"),
                    active_profile="P2",
                ),
                actor_id=administrator.id,
                correlation_id="plate-sync-2",
            )

            assert second.created_codes == ()
            assert second.active_plate_code == "P2"
            assert second.active_plate_changed is True
            assert await session.scalar(select(func.count(BuildPlate.id))) == 4
            assert await session.scalar(select(func.count(OutboxJob.id))) == 2
            assert await session.scalar(select(func.count(AuditEvent.id))) == 2

        await engine.dispose()
