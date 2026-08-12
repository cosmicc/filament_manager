"""PostgreSQL-backed workstation pairing and deployment lifecycle tests."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.api.routes import workstations
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import CuraDeploymentStatus, ProfileStatus, UserRole
from filament_manager.models.inventory import FilamentProduct, MaterialProfile, Printer, Vendor
from filament_manager.models.operations import AuditEvent
from filament_manager.models.workstations import CuraDeployment, WorkstationAgent
from filament_manager.security import hash_password


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pair_queue_claim_and_complete_workstation_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep enrollment one-time, credentials hashed, and deployment agent-scoped."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = Settings.model_validate(
            {
                "app": {
                    "base_url": "http://localhost",
                    "allowed_hosts": ["localhost"],
                    "secure_cookies": False,
                },
                "database": {"url": database_url},
                "spoolman": {"base_url": "http://spoolman.test:8000"},
                "moonraker": {
                    "printers": [
                        {
                            "id": "test-printer",
                            "name": "FLSUN V400",
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
                username="workstation-admin",
                normalized_username="workstation-admin",
                display_name="Workstation Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            vendor = Vendor(name="Test Filament")
            printer = Printer(
                printer_code="flsun-v400",
                name="FLSUN V400",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add_all([administrator, vendor, printer])
            await session.flush()
            product = FilamentProduct(
                vendor_id=vendor.id,
                material_type="PETG",
                product_name="Workshop PETG",
                color_name="Black",
                color_hex="111111",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.27"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add(product)
            await session.flush()
            profile = MaterialProfile(
                filament_product_id=product.id,
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                version=1,
                status=ProfileStatus.PUBLISHED,
                extruder_temp_c=Decimal("220"),
                bed_temp_c=Decimal("70"),
                flow_percent=Decimal("98"),
                cooling_min_percent=Decimal("20"),
                cooling_max_percent=Decimal("70"),
                pressure_advance=Decimal("0.035"),
                filament_density_g_cm3=Decimal("1.27"),
                checksum="a" * 64,
                published_at=datetime.now(UTC),
            )
            session.add(profile)
            await session.commit()
            profile_id = profile.id

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "workstation-admin"))
                assert user is not None
                return user

        monkeypatch.setattr(workstations, "get_settings", lambda: settings)
        from filament_manager import config as config_module
        from filament_manager import main

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        monkeypatch.setattr(main, "get_settings", lambda: settings)
        application = main.create_app()
        application.dependency_overrides[dependencies.session_dependency] = session_override
        application.dependency_overrides[dependencies.current_user] = user_override

        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            code_response = await client.post("/api/v1/workstation-agents/pairing-codes")
            assert code_response.status_code == 201, code_response.text
            pairing_code = code_response.json()["pairing_code"]
            pair_response = await client.post(
                "/api/v1/workstation-agent/pair",
                json={
                    "pairing_code": pairing_code,
                    "display_name": "Arch Cura",
                    "hostname": "workshop-arch",
                    "platform": "arch_linux",
                    "architecture": "x86_64",
                    "agent_version": "0.1.0",
                    "capabilities": {
                        "atomic_install": True,
                        "unmanaged_material_count": 0,
                    },
                    "cura_installations": [
                        {
                            "installation_id": "cura-test",
                            "version": "5.13",
                            "channel": "Linux Cura",
                            "path_hint": "Linux Cura user data / 5.13",
                            "setting_version": 27,
                            "machines": [
                                {
                                    "machine_id": "flsun-v400",
                                    "display_name": "FLSUN V400",
                                    "definition_id": "flsun_v400",
                                    "nozzle_diameter_mm": "0.4",
                                }
                            ],
                        }
                    ],
                },
            )
            assert pair_response.status_code == 201, pair_response.text
            agent_token = pair_response.json()["agent_token"]
            replay = await client.post(
                "/api/v1/workstation-agent/pair",
                json={
                    "pairing_code": pairing_code,
                    "display_name": "Replay",
                    "hostname": "replay",
                    "platform": "arch_linux",
                    "architecture": "x86_64",
                    "agent_version": "0.1.0",
                },
            )
            assert replay.status_code == 401
            queued = await client.post(f"/api/v1/profiles/{profile_id}/deployments", json={})
            assert queued.status_code == 201, queued.text
            deployment_id = queued.json()[0]["id"]
            claimed = await client.post(
                "/api/v1/workstation-agent/deployments/claim",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            assert claimed.status_code == 200, claimed.text
            assert claimed.json()["deployment_id"] == deployment_id
            assert claimed.json()["payload"]["schema_version"] == 2
            assert claimed.json()["payload"]["hide_bundled_materials"] is True
            completed = await client.post(
                f"/api/v1/workstation-agent/deployments/{deployment_id}/complete",
                headers={"Authorization": f"Bearer {agent_token}"},
                json={"outcome": "succeeded", "result": {"managed_files": 4}},
            )
            assert completed.status_code == 204, completed.text

        async with factory() as session:
            agent = await session.scalar(select(WorkstationAgent))
            assert agent is not None
            assert agent.token_hash != agent_token
            deployment = await session.get(CuraDeployment, deployment_id)
            assert deployment is not None
            assert deployment.status == CuraDeploymentStatus.SUCCEEDED
            assert await session.scalar(select(func.count(AuditEvent.id))) == 4

        await engine.dispose()
