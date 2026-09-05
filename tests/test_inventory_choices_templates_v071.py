"""Real PostgreSQL coverage for durable dropdowns and safe template correction."""

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.api.routes import inventory
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.models.inventory import MaterialProfile, Nozzle, Printer
from filament_manager.services import events


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("multiple_scopes", [False, True])
async def test_choices_search_and_template_correction(
    monkeypatch: pytest.MonkeyPatch,
    multiple_scopes: bool,
) -> None:
    """Preserve overrides and old snapshots, with atomic conflicts and durable choices."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
        settings = integration_settings(url)
        engine = create_async_engine(url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            user = User(
                username="tester",
                normalized_username="tester",
                display_name="Tester",
                password_hash="unused",
                role=UserRole.ADMINISTRATOR,
            )
            printer = Printer(
                printer_code="test-printer",
                name="Test Printer",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add_all([user, printer])
            await session.flush()
            nozzle = Nozzle(
                nozzle_code="NZ-040", printer_id=printer.id, diameter_mm=Decimal("0.4"), material="Brass"
            )
            session.add(nozzle)
            await session.commit()

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            return user

        from filament_manager import config, main

        for module in (config, main, inventory, events):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        app.dependency_overrides[dependencies.current_user] = user_override
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for kind, default in (("filler", "None"), ("finish", "Standard")):
                result = await client.get(f"/api/v1/filament-attributes?kind={kind}")
                assert result.status_code == 200, result.text
                assert default in [item["name"] for item in result.json()]
                result = await client.post(
                    "/api/v1/filament-attributes", json={"kind": kind, "name": "  Velvet  "}
                )
                assert result.status_code == 201, result.text
                duplicate = await client.post(
                    "/api/v1/filament-attributes", json={"kind": kind, "name": "VELVET"}
                )
                assert duplicate.json()["name"] == "Velvet"
                assert len((await client.get(f"/api/v1/filament-attributes?kind={kind}")).json()) == 2
            assert (
                await client.post("/api/v1/filament-attributes", json={"kind": "finish", "name": "  "})
            ).status_code == 422
            color = await client.post(
                "/api/v1/filament-colors", json={"name": "Custom Blue", "color_hex": "#1122ff"}
            )
            assert color.status_code == 201, color.text
            assert color.json()["color_hex"] == "1122FF"
            assert (
                await client.post(
                    "/api/v1/filament-colors", json={"name": "custom blue", "color_hex": "000000"}
                )
            ).status_code == 409
            assert (await client.get("/api/v1/filament-colors")).json()[0]["color_hex"] == "1122FF"
            manufacturer = await client.post("/api/v1/vendors", json={"name": "  Maker  "})
            assert manufacturer.status_code == 201, manufacturer.text
            assert (await client.post("/api/v1/vendors", json={"name": "maker"})).status_code == 409
            templates = []
            for material, bed in (("PLA", "60"), ("TPU", "45")):
                result = await client.post(
                    "/api/v1/profiles/templates",
                    json={
                        "name": f"Template {material}",
                        "material_type": material,
                        "printer_id": str(printer.id),
                        "nozzle_id": str(nozzle.id),
                        "nozzle_diameter_mm": "0.4",
                        "filament_diameter_mm": "1.75",
                        "settings": {
                            "extruder_temp_c": "210",
                            "bed_temp_c": bed,
                            "drying_temp_c": bed,
                            "flow_percent": "100",
                            "cooling_min_percent": "20",
                            "cooling_max_percent": "100",
                            "filament_density_g_cm3": "1.24",
                        },
                    },
                )
                assert result.status_code == 201, result.text
                templates.append(result.json())
            result = await client.post(
                "/api/v1/filaments",
                json={
                    "vendor_id": manufacturer.json()["id"],
                    "material_type": "PLA",
                    "color_name": "Custom Blue",
                    "filler": " \t",
                    "finish": None,
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.24",
                    "nominal_net_mass_g": "1000",
                    "material_template_revision_id": templates[0]["revisions"][0]["id"],
                },
            )
            assert result.status_code == 201, result.text
            product = result.json()
            assert (product["filler"], product["finish"]) == ("None", "Standard")
            result = await client.patch(
                f"/api/v1/filaments/{product['id']}",
                json={
                    "expected_version": product["record_version"],
                    "filler": "Carbon Fiber",
                    "finish": "Silk",
                },
            )
            assert result.status_code == 200, result.text
            product = result.json()
            result = await client.post(
                "/api/v1/spools",
                json={
                    "spool_code": "SEARCH",
                    "filament_product_id": product["id"],
                    "nominal_net_mass_g": "1000",
                    "tare_mass_g": "200",
                },
            )
            assert result.status_code == 201, result.text
            for term in ("BLUE", "carbon", "silk"):
                assert len((await client.get("/api/v1/filaments", params={"search": term})).json()) == 1
                assert (await client.get("/api/v1/spools", params={"search": term})).json()["total"] == 1
            profile = (await client.get("/api/v1/profiles")).json()[0]
            assert Decimal(profile["drying_temp_c"]) == 60
            custom_settings = {
                **templates[0]["revisions"][0]["settings"],
                "extruder_temp_c": "218",
                "drying_temp_c": "110",
            }
            result = await client.put(
                f"/api/v1/profiles/{profile['id']}/settings",
                json={
                    "expected_profile_version": profile["record_version"],
                    "settings": custom_settings,
                },
            )
            assert result.status_code == 200, result.text
            source = result.json()
            assert Decimal(source["drying_temp_c"]) == 60
            assert "drying_temp_c" not in source["override_keys"]
            assert not any("drying" in key for key in source["cura_settings"])
            payload = {
                "expected_profile_version": source["record_version"],
                "expected_filament_version": product["record_version"],
                "target_template_revision_id": templates[1]["revisions"][0]["id"],
            }
            if multiple_scopes:
                async with factory() as session:
                    larger = Nozzle(
                        nozzle_code="NZ-060",
                        printer_id=printer.id,
                        diameter_mm=Decimal("0.6"),
                        material="Brass",
                    )
                    session.add(larger)
                    await session.commit()
                for material in ("PLA", "TPU"):
                    result = await client.post(
                        "/api/v1/profiles/templates",
                        json={
                            "name": f"Template {material}",
                            "material_type": material,
                            "printer_id": str(printer.id),
                            "nozzle_id": str(larger.id),
                            "nozzle_diameter_mm": "0.6",
                            "filament_diameter_mm": "1.75",
                            "settings": {**templates[0]["revisions"][0]["settings"], "bed_temp_c": "50"},
                        },
                    )
                    assert result.status_code == 201, result.text
                    if material == "PLA":
                        added = await client.post(
                            "/api/v1/profiles/from-template",
                            json={
                                "filament_product_id": product["id"],
                                "material_template_revision_id": result.json()["revisions"][0]["id"],
                            },
                        )
                        assert added.status_code == 201, added.text
                        rejected = await client.post(
                            f"/api/v1/profiles/{source['id']}/change-template", json=payload
                        )
                        assert rejected.status_code == 409, rejected.text
                        assert rejected.json()["code"] == "matching_template_required"
                        unchanged = (await client.get(f"/api/v1/filaments/{product['id']}")).json()
                        assert (
                            unchanged["material_type"] == "PLA"
                            and unchanged["record_version"] == product["record_version"]
                        )
            result = await client.post(f"/api/v1/profiles/{source['id']}/change-template", json=payload)
            assert result.status_code == 201, result.text
            changed = result.json()
            assert Decimal(changed["extruder_temp_c"]) == 218
            assert Decimal(changed["bed_temp_c"]) == 45
            assert Decimal(changed["drying_temp_c"]) == 45
            assert "extruder_temp_c" in changed["override_keys"]
            assert "bed_temp_c" not in changed["override_keys"]
            assert changed["base_template_id"] == templates[1]["id"]
            assert (await client.get(f"/api/v1/filaments/{product['id']}")).json()["material_type"] == "TPU"
            assert (
                await client.post(f"/api/v1/profiles/{source['id']}/change-template", json=payload)
            ).status_code == 409
            async with factory() as session:
                old = await session.get(MaterialProfile, UUID(source["id"]))
                assert old is not None and old.base_template_revision_id == UUID(
                    templates[0]["revisions"][0]["id"]
                )
                assert old.bed_temp_c == 60 and old.extruder_temp_c == 218
                assert len(list(await session.scalars(select(MaterialProfile)))) == (
                    5 if multiple_scopes else 3
                )
            active = (await client.get("/api/v1/profiles")).json()
            assert all(item["base_template_name"] == "Template TPU" for item in active)
            user.role = UserRole.VIEWER
            assert (
                await client.post("/api/v1/filament-attributes", json={"kind": "finish", "name": "Denied"})
            ).status_code == 403
        await engine.dispose()
