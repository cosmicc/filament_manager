"""PostgreSQL-backed material-template and product inheritance tests."""

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import ProfileStatus, UserRole
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    Printer,
)
from filament_manager.security import hash_password
from filament_manager.services.cura_library import build_cura_library


@pytest.mark.integration
@pytest.mark.asyncio
async def test_published_template_starts_a_product_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A product inherits a copy while retaining immutable template provenance."""

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
                username="template-admin",
                normalized_username="template-admin",
                display_name="Template Administrator",
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
            await session.commit()
            printer_id = printer.id

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "template-admin"))
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
            created = await client.post(
                "/api/v1/profiles/templates",
                json={
                    "name": "Generic PCTPE",
                    "material_type": "PCTPE",
                    "description": "Starting settings for flexible PCTPE",
                    "printer_id": str(printer_id),
                    "nozzle_diameter_mm": "0.4",
                    "filament_diameter_mm": "1.75",
                    "settings": {
                        "extruder_temp_c": "245",
                        "bed_temp_c": "55",
                        "flow_percent": "100",
                        "cooling_enabled": True,
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "60",
                        "filament_density_g_cm3": "1.20",
                        "cura_extensions": {"retraction_enable": True},
                    },
                },
            )
            assert created.status_code == 201, created.text
            template = created.json()
            revision_id = template["revisions"][0]["id"]
            published = await client.post(
                f"/api/v1/profiles/templates/{template['id']}/revisions/{revision_id}/publish"
            )
            assert published.status_code == 200, published.text
            assert published.json()["status"] == "published"
            second_template = await client.post(
                "/api/v1/profiles/templates",
                json={
                    "name": "Generic TPU",
                    "material_type": "TPU",
                    "printer_id": str(printer_id),
                    "nozzle_diameter_mm": "0.4",
                    "filament_diameter_mm": "1.75",
                    "settings": {
                        "extruder_temp_c": "225",
                        "bed_temp_c": "45",
                        "flow_percent": "100",
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "80",
                        "filament_density_g_cm3": "1.21",
                    },
                },
            )
            assert second_template.status_code == 201, second_template.text
            conflicting_rename = await client.patch(
                f"/api/v1/profiles/templates/{second_template.json()['id']}",
                json={
                    "material_type": "pctpe",
                    "expected_version": second_template.json()["record_version"],
                },
            )
            assert conflicting_rename.status_code == 409, conflicting_rename.text
            assert conflicting_rename.json()["code"] == "material_template_scope_exists"
            product_response = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PCTPE",
                    "color_name": "Natural",
                    "product_name": "Taulman PCTPE",
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.21",
                    "nominal_net_mass_g": "500",
                    "material_template_revision_id": revision_id,
                },
            )
            assert product_response.status_code == 201, product_response.text
            product_id = product_response.json()["id"]

        async with factory() as session:
            template_row = await session.scalar(
                select(MaterialTemplate).where(MaterialTemplate.material_type == "PCTPE")
            )
            product = await session.get(FilamentProduct, product_id)
            profile = await session.scalar(
                select(MaterialProfile).where(MaterialProfile.filament_product_id == product_id)
            )
            assert template_row is not None and template_row.material_type == "PCTPE"
            assert product is not None and product.source_template_revision_id is not None
            assert profile is not None
            assert profile.status == ProfileStatus.DRAFT
            assert profile.source_template_revision_id == product.source_template_revision_id
            assert profile.extruder_temp_c == Decimal("245.00000")
            assert profile.filament_density_g_cm3 == Decimal("1.21000")
            library = await build_cura_library(session)
            assert library["schema_version"] == 2
            assert library["hide_bundled_materials"] is True
            materials = library["materials"]
            assert isinstance(materials, list) and len(materials) == 1
            assert materials[0]["source_kind"] == "template"
            assert materials[0]["material"]["material_type"] == "PCTPE"

        await engine.dispose()
