"""Real PostgreSQL tests for metadata concurrency, ratings, and activity pages."""

from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager import config, main
from filament_manager.api import dependencies
from filament_manager.api.routes import operations
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.models.inventory import BuildPlateSurface, FilamentProduct, MaterialTemplate, Printer
from filament_manager.models.operations import ApplicationSetting
from filament_manager.services import events
from filament_manager.services.google_workbook import snapshot
from filament_manager.services.material_settings import (
    create_published_profile_snapshot,
    save_template_settings,
)
from filament_manager.services.plate_ratings import filament_plate_rating
from filament_manager.services.seed import DEFAULT_ASA_SETTINGS, seed_configured_system


@pytest.mark.integration
@pytest.mark.asyncio
async def test_v083_metadata_ratings_and_pagination(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        settings = integration_settings(postgres.get_connection_url(), tmp_path)
        engine = create_async_engine(postgres.get_connection_url())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        for module in (config, main, operations, events):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        async with factory() as session:
            user = User(
                username="admin",
                normalized_username="admin",
                display_name="Admin",
                password_hash="unused",
                role=UserRole.ADMINISTRATOR,
            )
            session.add(user)
            await seed_configured_system(session, settings)
            printer = await session.scalar(select(Printer))
            side = await session.scalar(select(BuildPlateSurface))
            assert printer and side
            printer.active_plate_surface_id = side.id
            template = MaterialTemplate(
                name="Template PLA",
                material_type="PLA",
                printer_id=printer.id,
                nozzle_id=printer.active_nozzle_id,
                nozzle_diameter_mm=printer.nozzle_diameter_mm,
                filament_diameter_mm=Decimal("1.75"),
                active=True,
            )
            session.add(template)
            await session.flush()
            revision, _ = await save_template_settings(
                session, template=template, settings=DEFAULT_ASA_SETTINGS
            )
            product = FilamentProduct(
                product_name="PLA blue",
                material_type="PLA",
                color_name="Blue",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add(product)
            await session.flush()
            await create_published_profile_snapshot(
                session,
                filament_product_id=product.id,
                printer_id=printer.id,
                nozzle_diameter_mm=printer.nozzle_diameter_mm,
                base_revision=revision,
                settings=revision.settings,
            )
            await seed_configured_system(session, settings)
            families = set(await session.scalars(select(MaterialTemplate.material_type)))
            assert {"PLA", "Silk PLA", "PLA Carbon Fiber"} <= families
            assert product.material_type == "PLA"
            assert (await seed_configured_system(session, settings))["templates"] == 0
            session.add(ApplicationSetting(key="private.connection", value={"secret": "never-export-this"}))
            await session.commit()
            printer_id, template_id, side_id, product_id = printer.id, template.id, side.id, product.id

        async def sessions() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def current_user() -> User:
            return user

        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = sessions
        app.dependency_overrides[dependencies.current_user] = current_user
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as client:
            original = (await client.get("/api/v1/printers")).json()[0]
            async with factory() as session:
                printer = await session.get(Printer, printer_id)
                assert printer
                printer.record_version += 5
                printer.status = "idle"
                await session.commit()
            payload = {
                "expected_version": original["record_version"],
                "expected_settings_token": original["settings_token"],
                "max_extruder_temp_c": "300",
                "max_bed_temp_c": "120",
            }
            saved = await client.patch(f"/api/v1/printers/{printer_id}", json=payload)
            assert saved.status_code == 200, saved.text
            assert Decimal(saved.json()["max_bed_temp_c"]) == 120
            assert (
                await client.patch(f"/api/v1/printers/{printer_id}", json={**payload, "max_bed_temp_c": "90"})
            ).status_code == 409
            endpoint = f"/api/v1/build-plate-ratings/{template_id}"
            assert (await client.get(endpoint)).json()["ratings"] == {}
            saved_rating = await client.put(
                endpoint, json={"expected_version": 0, "ratings": {str(side_id): 0}}
            )
            assert saved_rating.status_code == 200, saved_rating.text
            assert (
                await client.put(endpoint, json={"expected_version": 0, "ratings": {str(side_id): 5}})
            ).status_code == 409
            assert (
                await client.put(endpoint, json={"expected_version": 1, "ratings": {str(side_id): True}})
            ).status_code == 422
            async with factory() as session:
                printer = await session.get(Printer, printer_id)
                assert printer
                assert await filament_plate_rating(session, printer, product_id) == 0
                unprofiled = FilamentProduct(
                    product_name="PLA calibration",
                    material_type="PLA",
                    color_name="Blue",
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                )
                session.add(unprofiled)
                await session.flush()
                assert await filament_plate_rating(session, printer, unprofiled.id) is None
                unprofiled.source_template_revision_id = revision.id
                await session.flush()
                assert await filament_plate_rating(session, printer, unprofiled.id) == 0
                tabs = await snapshot(session)
                assert next(tab for tab in tabs if tab.title == "Plate Ratings").rows[0][-1] == 0
                assert "never-export-this" not in str(tabs)
            compatibility = (
                await client.get(f"/api/v1/build-plate-ratings/filament/{product_id}?printer_id={printer_id}")
            ).json()
            assert compatibility[0]["ratings"][str(side_id)] == 0
            assert (await client.get("/api/v1/audit-events/page?per_page=21")).status_code == 422
            page = (
                await client.get("/api/v1/audit-events/page?per_page=20&search=plate_ratings&page=999")
            ).json()
            assert page["page"] == page["pages"] == 1
            assert page["total"] == 1
            assert UUID(page["items"][0]["id"])
            user.role = UserRole.VIEWER
            assert (
                await client.put(endpoint, json={"expected_version": 1, "ratings": {}})
            ).status_code == 403
        await engine.dispose()
