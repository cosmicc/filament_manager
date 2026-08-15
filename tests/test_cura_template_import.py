"""PostgreSQL-backed atomic Cura takeover workflow tests."""

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import CuraDeploymentStatus, UserRole
from filament_manager.models.inventory import MaterialProfile, Printer
from filament_manager.models.workstations import (
    CuraDeployment,
    CuraTakeoverMapping,
    WorkstationAgent,
)
from filament_manager.security import hash_password


def _settings(database_url: str) -> Settings:
    """Build isolated application settings for the takeover API."""

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
async def test_atomic_cura_source_mapping_completes_takeover_and_preserves_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One confirmation applies selected mappings and starts synchronization atomically."""

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
                agent_version="0.2.2",
                token_hash="a" * 64,
                enabled=True,
                cura_management_enabled=False,
                capabilities={
                    "unmanaged_import_source_count": 2,
                    "unmanaged_material_count": 0,
                    "unmanaged_print_profile_count": 2,
                },
                cura_installations=[
                    {
                        "installation_id": "cura-test",
                        "version": "5.13",
                        "channel": "Linux Cura",
                        "path_hint": "Linux Cura user data / 5.13",
                        "setting_version": 27,
                        "managed_library_checksum": None,
                        "machines": [],
                    }
                ],
                cura_materials=[
                    {
                        "source_id": "b" * 64,
                        "installation_id": "cura-test",
                        "name": "Normal PETG",
                        "brand": "Cura print profile",
                        "material_type": "Not assigned",
                        "color_name": "Not applicable",
                        "source_kind": "print_profile",
                        "machine_name": "Test Printer",
                        "quality_type": "normal",
                        "omitted_setting_count": 1,
                        "settings": {
                            "speed_print": "85",
                            "material_flow": "98.5",
                            "cool_fan_speed": "60",
                            "klipper_pressure_advance_factor": "0.035",
                        },
                    },
                    {
                        "source_id": "c" * 64,
                        "installation_id": "cura-test",
                        "name": "Unused Precision PETG",
                        "brand": "Cura print profile",
                        "material_type": "Not assigned",
                        "color_name": "Not applicable",
                        "source_kind": "print_profile",
                        "machine_name": "Test Printer",
                        "quality_type": "normal",
                        "omitted_setting_count": 0,
                        "settings": {"speed_print": "70"},
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
            template_response = await client.post(
                "/api/v1/profiles/templates",
                json={
                    "name": "Template PETG",
                    "material_type": "PETG",
                    "printer_id": str(printer_id),
                    "nozzle_diameter_mm": "0.4",
                    "filament_diameter_mm": "1.75",
                    "settings": {
                        "extruder_temp_c": "225",
                        "bed_temp_c": "70",
                        "flow_percent": "100",
                        "print_speed_mm_s": "60",
                        "cooling_enabled": True,
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "70",
                        "filament_density_g_cm3": "1.27",
                    },
                },
            )
            assert template_response.status_code == 201, template_response.text
            template = template_response.json()
            product_response = await client.post(
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
            assert product_response.status_code == 201, product_response.text
            product_id = product_response.json()["id"]
            profiles_response = await client.get("/api/v1/profiles")
            profile = next(
                item for item in profiles_response.json() if item["filament_product_id"] == product_id
            )
            customized_settings = {
                key: profile[key]
                for key in (
                    "chamber_temp_c",
                    "extruder_temp_c",
                    "bed_temp_c",
                    "flow_percent",
                    "print_speed_mm_s",
                    "outer_wall_speed_mm_s",
                    "inner_wall_speed_mm_s",
                    "infill_speed_mm_s",
                    "top_bottom_speed_mm_s",
                    "initial_layer_speed_mm_s",
                    "travel_speed_mm_s",
                    "support_speed_mm_s",
                    "retraction_distance_mm",
                    "retraction_speed_mm_s",
                    "cooling_enabled",
                    "cooling_min_percent",
                    "cooling_max_percent",
                    "support_overhang_angle_deg",
                    "tree_max_branch_angle_deg",
                    "pressure_advance",
                    "filament_density_g_cm3",
                    "preferred_build_plate_surface_id",
                    "cura_extensions",
                )
            }
            customized_settings["flow_percent"] = "97"
            saved_profile = await client.put(
                f"/api/v1/profiles/{profile['id']}/settings",
                json={
                    "expected_profile_version": profile["record_version"],
                    "settings": customized_settings,
                },
            )
            assert saved_profile.status_code == 200, saved_profile.text

            blocked_manual_enable = await client.patch(
                f"/api/v1/workstation-agents/{agent_id}",
                json={"expected_version": 1, "cura_management_enabled": True},
            )
            assert blocked_manual_enable.status_code == 409
            assert blocked_manual_enable.json()["code"] == "cura_takeover_required"
            unconfirmed = await client.post(
                f"/api/v1/workstation-agents/{agent_id}/cura-takeover",
                json={
                    "expected_agent_version": 1,
                    "confirmed": False,
                    "mappings": [],
                },
            )
            assert unconfirmed.status_code == 422

            takeover = await client.post(
                f"/api/v1/workstation-agents/{agent_id}/cura-takeover",
                json={
                    "expected_agent_version": 1,
                    "confirmed": True,
                    "mappings": [{"source_id": "b" * 64, "template_id": template["id"]}],
                },
            )
            assert takeover.status_code == 200, takeover.text
            assert takeover.json()["cura_management_enabled"] is True

            current_template = await client.get("/api/v1/profiles/templates?include_inactive=true")
            template_settings = next(
                item for item in current_template.json() if item["id"] == template["id"]
            )["revisions"][0]["settings"]
            assert template_settings["print_speed_mm_s"] == "85"
            assert template_settings["flow_percent"] == "98.5"
            current_profiles = await client.get("/api/v1/profiles")
            inherited = next(
                item for item in current_profiles.json() if item["filament_product_id"] == product_id
            )
            assert inherited["status"] == "published"
            assert Decimal(inherited["print_speed_mm_s"]) == Decimal("85")
            assert Decimal(inherited["flow_percent"]) == Decimal("97")
            assert set(inherited["override_keys"]) == {"flow_percent"}

            repeated = await client.post(
                f"/api/v1/workstation-agents/{agent_id}/cura-takeover",
                json={
                    "expected_agent_version": takeover.json()["record_version"],
                    "confirmed": True,
                    "mappings": [],
                },
            )
            assert repeated.status_code == 409
            assert repeated.json()["code"] == "cura_takeover_complete"

        async with factory() as session:
            mapping = await session.scalar(select(CuraTakeoverMapping))
            assert mapping is not None
            assert mapping.source_id == "b" * 64
            assert str(mapping.template_id) == template["id"]
            assert await session.scalar(select(func.count(CuraTakeoverMapping.id))) == 1
            assert await session.scalar(select(func.count(MaterialProfile.id))) == 3
            deployment = await session.scalar(select(CuraDeployment))
            assert deployment is not None
            assert deployment.status == CuraDeploymentStatus.PENDING

        await engine.dispose()
