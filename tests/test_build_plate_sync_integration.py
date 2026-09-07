"""PostgreSQL-backed build-plate synchronization tests."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api.errors import ApiError
from filament_manager.api.routes.plates import _require_idle_plate_context
from filament_manager.clients.moonraker import MoonrakerBedMeshState, MoonrakerClient, MoonrakerError
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import (
    PlateCondition,
    PlateStatus,
    PlateSurfaceTexture,
    PrintJobStatus,
    UserRole,
)
from filament_manager.models.inventory import BuildPlate, BuildPlateSurface, Printer
from filament_manager.models.operations import AuditEvent, BuildPlateMaintenanceEvent, OutboxJob
from filament_manager.models.printing import PrintJob
from filament_manager.security import hash_password
from filament_manager.services import events
from filament_manager.services.build_plate_sync import synchronize_build_plates
from filament_manager.services.print_statistics import last_build_plate_prints
from filament_manager.workers import dispatcher


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
                    integration_available=True,
                    selected_profile="P2",
                    selection_origin="manual",
                    selection_sequence=1,
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

            selected_surface = await session.get(BuildPlateSurface, printer.active_plate_surface_id)
            assert selected_surface is not None
            activated_at = selected_surface.last_activated_at
            assert activated_at is not None
            calibrated_at = datetime(2026, 9, 1, tzinfo=UTC)

            # Empty loaded state is a restart, not a physical plate removal.
            async def reconcile(**changes: object):
                values = {
                    "profile_names": ("P1", "P2", "P10b"),
                    "active_profile": None,
                    "integration_available": True,
                    "selected_profile": "P2",
                    "print_state": "standby",
                    "selection_origin": "restore",
                    "selection_sequence": 1,
                }
                values.update(changes)
                return await synchronize_build_plates(
                    session,
                    printer_id=printer.id,
                    mesh_state=MoonrakerBedMeshState(**values),
                    actor_id=None,
                    correlation_id="plate-restart",
                )

            restored = await reconcile(calibration_receipts=(("P2", 1, calibrated_at),))
            assert restored.restore_required is True
            assert restored.desired_mesh_profile == "P2"
            assert restored.active_plate_changed is False
            assert selected_surface.last_activated_at == activated_at
            assert selected_surface.last_mesh_calibrated_at == calibrated_at
            assert await session.scalar(select(func.count(BuildPlateMaintenanceEvent.id))) == 1
            await reconcile(active_profile="P2", calibration_receipts=(("P2", 1, calibrated_at),))
            assert await session.scalar(select(func.count(BuildPlateMaintenanceEvent.id))) == 1
            assert (await reconcile(print_state="printing")).restore_required is False
            assert (await reconcile(print_state="paused")).restore_required is False
            assert (await reconcile(calibrating=True)).restore_required is False
            assert (await reconcile(profile_names=("P1",))).restore_required is False
            assert printer.active_plate_surface_id == selected_surface.id
            # A newer offline receipt must not reuse the preceding exact date.
            await reconcile(calibration_receipts=(("P2", 2, None),))
            assert selected_surface.last_mesh_calibrated_at is None
            assert selected_surface.last_mesh_observed_at is not None
            session.add(
                PrintJob(
                    printer_id=printer.id,
                    filename="test.gcode",
                    status=PrintJobStatus.FAILED,
                    build_plate_id=selected_surface.build_plate_id,
                    build_plate_surface_id=selected_surface.id,
                    started_at=calibrated_at,
                )
            )
            await session.commit()
            plate_dates, side_dates = await last_build_plate_prints(session)
            assert plate_dates[selected_surface.build_plate_id] == calibrated_at
            assert side_dates[selected_surface.id] == calibrated_at
            cleared = await reconcile(selected_profile=None, selection_origin="manual", selection_sequence=2)
            assert cleared.active_plate_code is None
            assert printer.active_plate_surface_id is None

            active_job = await session.scalar(select(PrintJob))
            assert active_job is not None
            active_job.status = PrintJobStatus.IN_PROGRESS
            await session.flush()
            with pytest.raises(ApiError, match="idle printer"):
                await _require_idle_plate_context(session, printer.id)
            active_job.status = PrintJobStatus.FAILED
            await session.flush()
            await _require_idle_plate_context(session, printer.id)

            monkeypatch.setattr(dispatcher, "get_settings", lambda: settings)
            printer.active_plate_id = selected_surface.build_plate_id
            printer.active_plate_surface_id = selected_surface.id
            calls: list[str] = []

            async def select_mesh(_self, code: str):
                calls.append(code)

            async def clear_mesh(_self):
                calls.append("clear")

            monkeypatch.setattr(MoonrakerClient, "select_build_plate", select_mesh)
            monkeypatch.setattr(MoonrakerClient, "clear_build_plate", clear_mesh)

            def request(kind: str, key: str):
                return events.add_outbox_job(
                    session,
                    job_type=f"moonraker.build_plate.{kind}",
                    idempotency_key=key,
                    aggregate_type="printer",
                    aggregate_id=printer.id,
                    aggregate_version=printer.record_version,
                    payload={
                        "printer_id": str(printer.id),
                        "plate_code": "P2",
                        "expected_surface_id": str(selected_surface.id),
                    },
                )

            old_clear = request("clear", "old-clear")
            latest_select = request("select", "latest-select")
            await session.commit()
            await dispatcher.dispatch_job(session, old_clear)
            assert calls == []
            assert printer.active_plate_surface_id == selected_surface.id
            await dispatcher.dispatch_job(session, latest_select)
            assert calls == ["P2"]
            latest_clear = request("clear", "latest-clear")
            await session.commit()

            async def fail_clear(_self):
                raise MoonrakerError("Unavailable")

            monkeypatch.setattr(MoonrakerClient, "clear_build_plate", fail_clear)
            with pytest.raises(MoonrakerError):
                await dispatcher.dispatch_job(session, latest_clear)
            assert printer.active_plate_surface_id == selected_surface.id
            monkeypatch.setattr(MoonrakerClient, "clear_build_plate", clear_mesh)
            await dispatcher.dispatch_job(session, latest_clear)
            assert printer.active_plate_surface_id is None
            assert calls == ["P2", "clear"]

        await engine.dispose()
