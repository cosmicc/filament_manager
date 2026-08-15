"""PostgreSQL-backed workstation pairing and deployment lifecycle tests."""

import json
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
from filament_manager.domain.spool_preflight import cura_material_guid
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import CuraDeploymentStatus, ProfileStatus, UserRole
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Vendor,
)
from filament_manager.models.operations import AuditEvent
from filament_manager.models.workstations import (
    CuraDeployment,
    CuraManagedEditReceipt,
    WorkstationAgent,
)
from filament_manager.security import hash_password


def test_combined_cura_import_source_count_prevents_automatic_takeover() -> None:
    """Saved print profiles block automatic takeover even without user materials."""

    assert (
        workstations._unmanaged_cura_source_count(
            {"unmanaged_material_count": 0, "unmanaged_import_source_count": 2}
        )
        == 2
    )
    assert workstations._unmanaged_cura_source_count({"unmanaged_material_count": 0}) == 0
    assert workstations._unmanaged_cura_source_count({"unmanaged_material_count": True}) is None


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
            template = MaterialTemplate(
                name="Template PETG",
                material_type="PETG",
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                filament_diameter_mm=Decimal("1.75"),
                active=True,
            )
            session.add(template)
            await session.flush()
            template_revision = MaterialTemplateRevision(
                material_template_id=template.id,
                version=1,
                status=ProfileStatus.PUBLISHED,
                settings={
                    "extruder_temp_c": "220",
                    "bed_temp_c": "70",
                    "flow_percent": "98",
                    "cooling_enabled": True,
                    "cooling_min_percent": "20",
                    "cooling_max_percent": "70",
                    "filament_density_g_cm3": "1.27",
                    "pressure_advance": "0.035",
                    "cura_extensions": {},
                },
                checksum="b" * 64,
                published_at=datetime.now(UTC),
            )
            session.add(template_revision)
            await session.flush()
            product.source_template_revision_id = template_revision.id
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
                base_template_revision_id=template_revision.id,
                setting_overrides={},
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
            edited = await client.post(
                "/api/v1/workstation-agent/heartbeat",
                headers={"Authorization": f"Bearer {agent_token}"},
                json={
                    "agent_version": "0.2.0",
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
                            "managed_library_checksum": "a" * 64,
                            "machines": [],
                        }
                    ],
                    "cura_managed_materials": [
                        {
                            "source_id": "c" * 64,
                            "installation_id": "cura-test",
                            "name": "Test Filament PETG · Black",
                            "brand": "Test Filament",
                            "material_type": "PETG",
                            "color_name": "Black",
                            "material_guid": cura_material_guid("product", profile_id),
                            "content_checksum": "d" * 64,
                            "settings": {
                                "material_print_temperature": "225",
                                "material_bed_temperature": "70",
                                "material_flow": "98",
                                "cool_fan_enabled": True,
                                "cool_fan_speed_min": "20",
                                "cool_fan_speed_max": "70",
                                "klipper_pressure_advance_factor": "0.035",
                            },
                        }
                    ],
                },
            )
            assert edited.status_code == 204, edited.text
            edited_again = await client.post(
                "/api/v1/workstation-agent/heartbeat",
                headers={"Authorization": f"Bearer {agent_token}"},
                json=json.loads(edited.request.content),
            )
            assert edited_again.status_code == 204, edited_again.text

        async with factory() as session:
            agent = await session.scalar(select(WorkstationAgent))
            assert agent is not None
            assert agent.token_hash != agent_token
            deployment = await session.get(CuraDeployment, deployment_id)
            assert deployment is not None
            assert deployment.status == CuraDeploymentStatus.SUCCEEDED
            queued_current_library = await session.scalar(
                select(CuraDeployment)
                .where(CuraDeployment.id != deployment_id)
                .order_by(CuraDeployment.created_at.desc())
                .limit(1)
            )
            assert queued_current_library is not None
            assert queued_current_library.status == CuraDeploymentStatus.PENDING
            current_profile = await session.scalar(
                select(MaterialProfile)
                .where(MaterialProfile.filament_product_id == profile.filament_product_id)
                .order_by(MaterialProfile.version.desc())
                .limit(1)
            )
            assert current_profile is not None and current_profile.version == 2
            assert current_profile.status == ProfileStatus.PUBLISHED
            assert current_profile.extruder_temp_c == Decimal("225.00000")
            assert current_profile.base_template_revision_id == template_revision.id
            receipt = await session.scalar(select(CuraManagedEditReceipt))
            assert receipt is not None
            assert receipt.content_checksum != "d" * 64
            assert await session.scalar(select(func.count(CuraManagedEditReceipt.id))) == 1
            assert await session.scalar(select(func.count(AuditEvent.id))) == 5

        await engine.dispose()
