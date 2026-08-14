"""PostgreSQL-backed Cura material preservation workflow tests."""

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.models.inventory import Printer
from filament_manager.models.workstations import WorkstationAgent
from filament_manager.security import hash_password


def _settings(database_url: str) -> Settings:
    """Build isolated application settings for the import API."""

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
async def test_cura_material_import_blocks_takeover_until_template_is_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selected local material content must enter the published desired library before takeover."""

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
                username="cura-template-admin",
                normalized_username="cura-template-admin",
                display_name="Cura Template Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            printer = Printer(
                printer_code="test-printer",
                name="Test Printer",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add_all([administrator, printer])
            await session.flush()
            agent = WorkstationAgent(
                agent_code="WS-CURA-IMPORT",
                display_name="Workshop Cura",
                hostname="workshop",
                platform="arch_linux",
                architecture="x86_64",
                agent_version="0.2.0",
                token_hash="a" * 64,
                enabled=True,
                cura_management_enabled=False,
                capabilities={"unmanaged_material_count": 1},
                cura_installations=[],
                cura_materials=[
                    {
                        "source_id": "b" * 64,
                        "installation_id": "cura-test",
                        "name": "Polymaker PETG - PolyLite",
                        "brand": "Polymaker",
                        "material_type": "PETG",
                        "color_name": "Black",
                        "settings": {
                            "default_material_print_temperature": "225",
                            "default_material_bed_temperature": "70",
                            "material_flow": "98.5",
                            "cool_fan_speed": "60",
                            "klipper_pressure_advance_factor": "0.035",
                        },
                    },
                    {
                        "source_id": "c" * 64,
                        "installation_id": "cura-test",
                        "name": "Overture PETG - Tuned",
                        "brand": "Overture",
                        "material_type": "PETG",
                        "color_name": "Blue",
                        "settings": {
                            "default_material_print_temperature": "230",
                            "default_material_bed_temperature": "75",
                            "material_flow": "99",
                            "cool_fan_speed": "50",
                        },
                    },
                ],
                created_by=administrator.id,
            )
            session.add(agent)
            await session.commit()
            administrator_id = administrator.id
            printer_id = printer.id
            agent_id = agent.id

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

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        monkeypatch.setattr(main, "get_settings", lambda: settings)
        application = main.create_app()
        application.dependency_overrides[dependencies.session_dependency] = session_override
        application.dependency_overrides[dependencies.current_user] = user_override

        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            imported = await client.post(
                "/api/v1/profiles/templates/import-cura-material",
                json={
                    "agent_id": str(agent_id),
                    "source_id": "b" * 64,
                    "name": "Imported PolyLite PETG",
                    "material_type": "PETG",
                    "printer_id": str(printer_id),
                    "nozzle_diameter_mm": "0.4",
                    "filament_diameter_mm": "1.75",
                    "filament_density_g_cm3": "1.27",
                },
            )
            assert imported.status_code == 201, imported.text
            template = imported.json()
            assert template["source_workstation_agent_id"] == str(agent_id)
            assert template["source_cura_material_id"] == "b" * 64
            assert template["revisions"][0]["status"] == "draft"
            assert template["revisions"][0]["settings"]["extruder_temp_c"] == "225"
            assert template["revisions"][0]["settings"]["flow_percent"] == "98.5"
            assert template["revisions"][0]["settings"]["filament_density_g_cm3"] == "1.27"

            conflicting_app_template = await client.post(
                "/api/v1/profiles/templates",
                json={
                    "name": "Another PETG template",
                    "material_type": "petg",
                    "printer_id": str(printer_id),
                    "nozzle_diameter_mm": "0.4",
                    "filament_diameter_mm": "1.75",
                    "settings": template["revisions"][0]["settings"],
                },
            )
            assert conflicting_app_template.status_code == 409
            assert conflicting_app_template.json()["code"] == "material_template_scope_exists"

            duplicate = await client.post(
                "/api/v1/profiles/templates/import-cura-material",
                json={
                    "agent_id": str(agent_id),
                    "source_id": "b" * 64,
                    "name": "Duplicate",
                    "material_type": "PETG",
                    "printer_id": str(printer_id),
                    "nozzle_diameter_mm": "0.4",
                    "filament_density_g_cm3": "1.27",
                },
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["code"] == "cura_material_already_imported"

            blocked = await client.patch(
                f"/api/v1/workstation-agents/{agent_id}",
                json={"expected_version": 1, "cura_management_enabled": True},
            )
            assert blocked.status_code == 409
            assert blocked.json()["code"] == "cura_template_imports_unpublished"

            published = await client.post(
                f"/api/v1/profiles/templates/{template['id']}/revisions/"
                f"{template['revisions'][0]['id']}/publish"
            )
            assert published.status_code == 200, published.text

            product = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PETG",
                    "color_name": "Blue",
                    "product_name": "Overture PETG",
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.27",
                    "nominal_net_mass_g": "1000",
                    "material_template_revision_id": template["revisions"][0]["id"],
                },
            )
            assert product.status_code == 201, product.text
            imported_profile = await client.post(
                "/api/v1/profiles/import-cura-material",
                json={
                    "agent_id": str(agent_id),
                    "source_id": "c" * 64,
                    "filament_product_id": product.json()["id"],
                    "printer_id": str(printer_id),
                    "nozzle_diameter_mm": "0.4",
                },
            )
            assert imported_profile.status_code == 201, imported_profile.text
            profile = imported_profile.json()
            assert profile["status"] == "draft"
            assert profile["source_workstation_agent_id"] == str(agent_id)
            assert profile["source_cura_material_id"] == "c" * 64

            blocked_by_profile = await client.patch(
                f"/api/v1/workstation-agents/{agent_id}",
                json={"expected_version": 1, "cura_management_enabled": True},
            )
            assert blocked_by_profile.status_code == 409
            assert blocked_by_profile.json()["code"] == "cura_template_imports_unpublished"

            cross_type_duplicate = await client.post(
                "/api/v1/profiles/templates/import-cura-material",
                json={
                    "agent_id": str(agent_id),
                    "source_id": "c" * 64,
                    "name": "Duplicate profile source",
                    "material_type": "PETG",
                    "printer_id": str(printer_id),
                    "nozzle_diameter_mm": "0.4",
                    "filament_density_g_cm3": "1.27",
                },
            )
            assert cross_type_duplicate.status_code == 409
            assert cross_type_duplicate.json()["code"] == "cura_material_already_imported"

            published_profile = await client.post(f"/api/v1/profiles/{profile['id']}/publish")
            assert published_profile.status_code == 200, published_profile.text
            enabled = await client.patch(
                f"/api/v1/workstation-agents/{agent_id}",
                json={"expected_version": 1, "cura_management_enabled": True},
            )
            assert enabled.status_code == 200, enabled.text
            assert enabled.json()["cura_management_enabled"] is True

        await engine.dispose()
