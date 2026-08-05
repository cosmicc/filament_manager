"""PostgreSQL-backed API transaction tests."""

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.api.routes import inventory
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import SpoolStatus, UserRole
from filament_manager.models.inventory import FilamentProduct, Spool, SpoolMeasurement, Vendor
from filament_manager.models.operations import AuditEvent, OutboxJob
from filament_manager.security import hash_password
from filament_manager.services import events


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_tare_measurement_is_one_audited_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Establish tare, measurement, spool state, audit, and projections atomically."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = Settings.model_validate(
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
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            administrator = User(
                username="integration-admin",
                normalized_username="integration-admin",
                display_name="Integration Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            vendor = Vendor(name="Test Vendor")
            session.add_all([administrator, vendor])
            await session.flush()
            product = FilamentProduct(
                vendor_id=vendor.id,
                material_type="PETG",
                color_name="Black",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.27"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add(product)
            await session.flush()
            spool = Spool(
                spool_code="TEST-1",
                filament_product_id=product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("0"),
                remaining_mass_expected_g=Decimal("1000"),
                remaining_mass_effective_g=Decimal("1000"),
                weight_confidence="unknown_tare",
                status=SpoolStatus.NEEDS_WEIGHING,
            )
            session.add(spool)
            await session.commit()
            spool_id = spool.id

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "integration-admin"))
                assert user is not None
                return user

        monkeypatch.setattr(inventory, "get_settings", lambda: settings)
        monkeypatch.setattr(events, "get_settings", lambda: settings)
        from filament_manager import config as config_module

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        from filament_manager import main

        monkeypatch.setattr(main, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        app.dependency_overrides[dependencies.current_user] = user_override

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                f"/api/v1/spools/{spool_id}/measurements",
                headers={"Idempotency-Key": "integration-measurement-001"},
                json={"gross_mass_g": "1012.4", "tare_mass_g": "212.4", "source": "manual"},
            )

        assert response.status_code == 201, response.text
        assert response.json()["net_mass_g"] == "800.000"
        async with factory() as session:
            stored_spool = await session.get(Spool, spool_id)
            assert stored_spool is not None
            assert stored_spool.tare_mass_g == Decimal("212.400")
            assert stored_spool.remaining_mass_effective_g == Decimal("800.000")
            assert stored_spool.record_version == 2
            assert await session.scalar(select(func.count(SpoolMeasurement.id))) == 1
            assert await session.scalar(select(func.count(OutboxJob.id))) == 2
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "spool.measurement.accept")
            )
            assert audit is not None
            assert audit.object_id is not None

        await engine.dispose()
