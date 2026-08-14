"""PostgreSQL-backed physical-tooling and completed-print attribution tests."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import PrintJobStatus, SpoolStatus, UserRole
from filament_manager.models.inventory import (
    BuildPlate,
    BuildPlateSurface,
    FilamentProduct,
    Printer,
    Spool,
)
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.security import hash_password
from filament_manager.services import events


def _settings(database_url: str) -> Settings:
    """Return isolated settings for physical inventory API validation."""

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
async def test_physical_nozzle_side_b_and_distinct_completed_print_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Count only completed jobs and count each M600 spool once per print."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = _settings(database_url)
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            administrator = User(
                username="v022-admin",
                normalized_username="v022-admin",
                display_name="Version 0.2.2 Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            printer = Printer(
                printer_code="test-printer",
                name="Test Printer",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            plate = BuildPlate(plate_code="P1", display_name="Test Plate")
            product = FilamentProduct(
                material_type="PLA",
                color_name="Blue",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add_all([administrator, printer, plate, product])
            await session.flush()
            side_a = BuildPlateSurface(
                build_plate_id=plate.id,
                side="a",
                surface_code="P1",
                klipper_mesh_profile="P1",
                mesh_available=True,
            )
            spool_one = Spool(
                spool_code="V022-ONE",
                filament_product_id=product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("800"),
                remaining_mass_effective_g=Decimal("800"),
                weight_confidence="estimated",
                status=SpoolStatus.IN_STOCK,
            )
            spool_two = Spool(
                spool_code="V022-TWO",
                filament_product_id=product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("700"),
                remaining_mass_effective_g=Decimal("700"),
                weight_confidence="estimated",
                status=SpoolStatus.IN_STOCK,
            )
            session.add_all([side_a, spool_one, spool_two])
            await session.commit()
            administrator_id = administrator.id
            printer_id = printer.id
            plate_id = plate.id
            side_a_id = side_a.id
            spool_one_id = spool_one.id
            spool_two_id = spool_two.id

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.get(User, administrator_id)
                assert user is not None
                return user

        from filament_manager import config as config_module
        from filament_manager import main
        from filament_manager.api.routes import diagnostics as diagnostic_routes

        async def recovery_validation(_: AsyncSession) -> dict[str, object]:
            """Return deterministic validation evidence without external network calls."""

            checked_at = datetime.now(UTC)
            return {
                "summary": {"healthy": 1, "warning": 0, "error": 0, "disabled": 0},
                "checks": [
                    {
                        "key": "test.recovery",
                        "label": "Test recovery",
                        "category": "recovery",
                        "status": "healthy",
                        "detail": "Read-only validation completed",
                        "checked_at": checked_at,
                    }
                ],
                "completed_at": checked_at,
            }

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        monkeypatch.setattr(main, "get_settings", lambda: settings)
        monkeypatch.setattr(events, "get_settings", lambda: settings)
        monkeypatch.setattr(diagnostic_routes, "run_recovery_validation", recovery_validation)
        application = main.create_app()
        application.dependency_overrides[dependencies.session_dependency] = session_override
        application.dependency_overrides[dependencies.current_user] = user_override

        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created_nozzle = await client.post(
                "/api/v1/nozzles",
                json={
                    "nozzle_code": "NZ-040-HS",
                    "diameter_mm": "0.4",
                    "material": "Hardened steel",
                    "manufacturer": "Test Tooling",
                },
            )
            assert created_nozzle.status_code == 201, created_nozzle.text
            nozzle_id = created_nozzle.json()["id"]
            installed = await client.post(
                f"/api/v1/nozzles/{nozzle_id}/install",
                json={"printer_id": str(printer_id)},
            )
            assert installed.status_code == 200, installed.text
            assert installed.json()["installed_printer_id"] == str(printer_id)

            side_b = await client.post(f"/api/v1/build-plates/{plate_id}/surfaces", json={})
            assert side_b.status_code == 201, side_b.text
            side_b_payload = next(item for item in side_b.json()["surfaces"] if item["side"] == "b")
            assert side_b_payload["surface_code"] == "P1b"
            assert side_b_payload["klipper_mesh_profile"] == "P1b"
            assert side_b_payload["mesh_available"] is False
            duplicate_side_b = await client.post(f"/api/v1/build-plates/{plate_id}/surfaces", json={})
            assert duplicate_side_b.status_code == 409
            validation = await client.post("/api/v1/diagnostics/validation-runs")
            assert validation.status_code == 201, validation.text
            assert validation.json()["status"] == "completed"
            assert validation.json()["results"]["summary"]["healthy"] == 1
            validation_history = await client.get("/api/v1/diagnostics/validation-runs")
            assert validation_history.status_code == 200
            assert validation_history.json()[0]["id"] == validation.json()["id"]
            rebuilt = await client.post("/api/v1/diagnostics/projection-rebuild")
            assert rebuilt.status_code == 200, rebuilt.text
            assert rebuilt.json()["categories"] == {"spoolman": 1, "google": 0, "cura": 0}

        async with factory() as session:
            completed = PrintJob(
                printer_id=printer_id,
                filename="completed.gcode",
                source="live",
                status=PrintJobStatus.COMPLETED,
                spool_id=spool_one_id,
                build_plate_id=plate_id,
                build_plate_surface_id=side_a_id,
                nozzle_id=nozzle_id,
                actual_filament_weight_g=Decimal("12.5"),
                state_snapshot={},
                profile_snapshot={},
            )
            failed = PrintJob(
                printer_id=printer_id,
                filename="failed.gcode",
                source="live",
                status=PrintJobStatus.FAILED,
                spool_id=spool_two_id,
                build_plate_id=plate_id,
                build_plate_surface_id=side_a_id,
                nozzle_id=nozzle_id,
                actual_filament_weight_g=Decimal("99"),
                state_snapshot={},
                profile_snapshot={},
            )
            session.add_all([completed, failed])
            await session.flush()
            session.add_all(
                [
                    PrintMaterialSegment(
                        print_job_id=completed.id,
                        segment_number=1,
                        spool_id=spool_one_id,
                        source="preflight",
                        state_snapshot={},
                        started_at=datetime.now(UTC),
                        created_at=datetime.now(UTC),
                    ),
                    PrintMaterialSegment(
                        print_job_id=completed.id,
                        segment_number=2,
                        spool_id=spool_two_id,
                        source="m600",
                        state_snapshot={},
                        started_at=datetime.now(UTC),
                        created_at=datetime.now(UTC),
                    ),
                ]
            )
            await session.commit()

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            spools = await client.get("/api/v1/spools?limit=200")
            nozzles = await client.get("/api/v1/nozzles")
            plates = await client.get("/api/v1/build-plates")
        assert spools.status_code == 200, spools.text
        spool_counts = {item["spool_code"]: item["completed_print_count"] for item in spools.json()["items"]}
        assert spool_counts == {"V022-ONE": 1, "V022-TWO": 1}
        assert nozzles.status_code == 200, nozzles.text
        assert nozzles.json()[0]["completed_print_count"] == 1
        assert Decimal(nozzles.json()[0]["completed_filament_weight_g"]) == Decimal("12.5")
        assert plates.status_code == 200, plates.text
        plate_surfaces = {item["surface_code"]: item for item in plates.json()[0]["surfaces"]}
        assert plate_surfaces["P1"]["completed_print_count"] == 1
        assert plate_surfaces["P1b"]["completed_print_count"] == 0

        await engine.dispose()
