"""PostgreSQL regressions for filament profiles in multiple exact scopes."""

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.api.schemas import MaterialSettingsInput
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import NozzleStatus, UserRole
from filament_manager.models.inventory import MaterialTemplate, Nozzle, Printer
from filament_manager.security import hash_password
from filament_manager.services.material_settings import save_template_settings


def _template_payload(
    *, printer_id: str, nozzle_id: str, material: str, nozzle: str, temperature: str
) -> dict[str, object]:
    """Build one minimal valid direct-save template payload."""

    return {
        "name": f"Template {material} {nozzle}",
        "material_type": material,
        "printer_id": printer_id,
        "nozzle_id": nozzle_id,
        "nozzle_diameter_mm": nozzle,
        "filament_diameter_mm": "1.75",
        "settings": {
            "extruder_temp_c": temperature,
            "bed_temp_c": "60",
            "flow_percent": "100",
            "cooling_min_percent": "20",
            "cooling_max_percent": "100",
            "filament_density_g_cm3": "1.24",
        },
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_profile_creation_inheritance_density_and_duplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every mutation targets an exact scope instead of a global profile version."""

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
                            "id": "scope-printer",
                            "name": "Scope Printer",
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
                username="scope-admin",
                normalized_username="scope-admin",
                display_name="Scope Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            printer = Printer(
                printer_code="scope-printer",
                name="Scope Printer",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add_all([administrator, printer])
            await session.flush()
            physical_nozzles = [
                Nozzle(
                    nozzle_code=f"NZ-{diameter.replace('.', '')}",
                    printer_id=printer.id,
                    diameter_mm=Decimal(diameter),
                    material="Brass",
                    status=NozzleStatus.AVAILABLE,
                )
                for diameter in ("0.4", "0.6", "0.8")
            ]
            session.add_all(physical_nozzles)
            await session.commit()
            printer_id = str(printer.id)
            nozzle_ids = {
                diameter: str(nozzle.id)
                for diameter, nozzle in zip(("0.4", "0.6", "0.8"), physical_nozzles, strict=True)
            }

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "scope-admin"))
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
            template_04_response = await client.post(
                "/api/v1/profiles/templates",
                json=_template_payload(
                    printer_id=printer_id,
                    nozzle_id=nozzle_ids["0.4"],
                    material="PLA",
                    nozzle="0.4",
                    temperature="205",
                ),
            )
            template_06_response = await client.post(
                "/api/v1/profiles/templates",
                json=_template_payload(
                    printer_id=printer_id,
                    nozzle_id=nozzle_ids["0.6"],
                    material="PLA",
                    nozzle="0.6",
                    temperature="215",
                ),
            )
            abs_template_response = await client.post(
                "/api/v1/profiles/templates",
                json=_template_payload(
                    printer_id=printer_id,
                    nozzle_id=nozzle_ids["0.8"],
                    material="ABS",
                    nozzle="0.8",
                    temperature="245",
                ),
            )
            assert template_04_response.status_code == 201, template_04_response.text
            assert template_06_response.status_code == 201, template_06_response.text
            assert abs_template_response.status_code == 201, abs_template_response.text
            template_04 = template_04_response.json()
            template_06 = template_06_response.json()
            revision_04 = template_04["revisions"][0]["id"]
            revision_06 = template_06["revisions"][0]["id"]

            product_response = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PLA",
                    "color_name": "Blue",
                    "product_name": "Multi-scope PLA",
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.25",
                    "nominal_net_mass_g": "1000",
                    "material_template_revision_id": revision_04,
                },
            )
            assert product_response.status_code == 201, product_response.text
            product = product_response.json()

            unknown_product = await client.post(
                "/api/v1/profiles/from-template",
                json={
                    "filament_product_id": "00000000-0000-0000-0000-000000000001",
                    "material_template_revision_id": revision_06,
                },
            )
            assert unknown_product.status_code == 404
            assert unknown_product.json()["code"] == "unknown_filament"
            unknown_revision = await client.post(
                "/api/v1/profiles/from-template",
                json={
                    "filament_product_id": product["id"],
                    "material_template_revision_id": "00000000-0000-0000-0000-000000000001",
                },
            )
            assert unknown_revision.status_code == 422
            assert unknown_revision.json()["code"] == "template_revision_unavailable"

            wrong_material = await client.post(
                "/api/v1/profiles/from-template",
                json={
                    "filament_product_id": product["id"],
                    "material_template_revision_id": abs_template_response.json()["revisions"][0]["id"],
                },
            )
            assert wrong_material.status_code == 422
            assert wrong_material.json()["code"] == "material_type_template_mismatch"

            added = await client.post(
                "/api/v1/profiles/from-template",
                json={
                    "filament_product_id": product["id"],
                    "material_template_revision_id": revision_06,
                },
            )
            assert added.status_code == 201, added.text
            assert Decimal(added.json()["nozzle_diameter_mm"]) == Decimal("0.6")
            assert Decimal(added.json()["filament_density_g_cm3"]) == Decimal("1.25")
            duplicate_scope = await client.post(
                "/api/v1/profiles/from-template",
                json={
                    "filament_product_id": product["id"],
                    "material_template_revision_id": revision_06,
                },
            )
            assert duplicate_scope.status_code == 409
            assert duplicate_scope.json()["code"] == "profile_scope_exists"

            profiles_response = await client.get("/api/v1/profiles")
            scopes = {
                Decimal(profile["nozzle_diameter_mm"]): profile
                for profile in profiles_response.json()
                if profile["filament_product_id"] == product["id"]
            }
            assert set(scopes) == {Decimal("0.4"), Decimal("0.6")}
            original_04_id = scopes[Decimal("0.4")]["id"]

            updated_06_template = await client.put(
                f"/api/v1/profiles/templates/{template_06['id']}/settings",
                json={
                    "expected_template_version": template_06["record_version"],
                    "settings": {
                        **template_06["revisions"][0]["settings"],
                        "extruder_temp_c": "220",
                    },
                },
            )
            assert updated_06_template.status_code == 200, updated_06_template.text
            current_profiles = (await client.get("/api/v1/profiles")).json()
            scopes = {
                Decimal(profile["nozzle_diameter_mm"]): profile
                for profile in current_profiles
                if profile["filament_product_id"] == product["id"]
            }
            assert scopes[Decimal("0.4")]["id"] == original_04_id
            assert scopes[Decimal("0.4")]["version"] == 1
            assert scopes[Decimal("0.6")]["version"] == 2
            assert Decimal(scopes[Decimal("0.6")]["extruder_temp_c"]) == Decimal("220")

            density_update = await client.patch(
                f"/api/v1/filaments/{product['id']}",
                json={"expected_version": product["record_version"], "density_g_cm3": "1.30"},
            )
            assert density_update.status_code == 200, density_update.text
            density_profiles = (await client.get("/api/v1/profiles")).json()
            scopes = {
                Decimal(profile["nozzle_diameter_mm"]): profile
                for profile in density_profiles
                if profile["filament_product_id"] == product["id"]
            }
            assert scopes[Decimal("0.4")]["version"] == 2
            assert scopes[Decimal("0.6")]["version"] == 3
            assert {Decimal(profile["filament_density_g_cm3"]) for profile in scopes.values()} == {
                Decimal("1.30")
            }
            assert scopes[Decimal("0.4")]["base_template_revision_id"] == revision_04
            assert (
                scopes[Decimal("0.6")]["base_template_revision_id"]
                == updated_06_template.json()["revisions"][0]["id"]
            )

            customized_06 = await client.put(
                f"/api/v1/profiles/{scopes[Decimal('0.6')]['id']}/settings",
                json={
                    "expected_profile_version": scopes[Decimal("0.6")]["record_version"],
                    "settings": {
                        **{key: scopes[Decimal("0.6")][key] for key in MaterialSettingsInput.model_fields},
                        "bed_temp_c": "72",
                    },
                },
            )
            assert customized_06.status_code == 200, customized_06.text
            customized_04 = await client.put(
                f"/api/v1/profiles/{scopes[Decimal('0.4')]['id']}/settings",
                json={
                    "expected_profile_version": scopes[Decimal("0.4")]["record_version"],
                    "settings": {
                        **{key: scopes[Decimal("0.4")][key] for key in MaterialSettingsInput.model_fields},
                        "extruder_temp_c": "209",
                    },
                },
            )
            assert customized_04.status_code == 200, customized_04.text

            duplicated = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PLA",
                    "color_name": "Blue Copy",
                    "product_name": "Multi-scope PLA Copy",
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.30",
                    "nominal_net_mass_g": "1000",
                    "material_template_revision_id": updated_06_template.json()["revisions"][0]["id"],
                    "duplicate_source_filament_id": product["id"],
                },
            )
            assert duplicated.status_code == 201, duplicated.text
            duplicated_profiles = (await client.get("/api/v1/profiles")).json()
            duplicated_profile = next(
                profile
                for profile in duplicated_profiles
                if profile["filament_product_id"] == duplicated.json()["id"]
            )
            assert Decimal(duplicated_profile["nozzle_diameter_mm"]) == Decimal("0.6")
            assert Decimal(duplicated_profile["bed_temp_c"]) == Decimal("72")
            assert Decimal(duplicated_profile["extruder_temp_c"]) == Decimal("220")

            latest_template_06 = updated_06_template.json()
            propagated_06 = await client.put(
                f"/api/v1/profiles/templates/{template_06['id']}/settings",
                json={
                    "expected_template_version": latest_template_06["record_version"],
                    "settings": {
                        **latest_template_06["revisions"][0]["settings"],
                        "extruder_temp_c": "225",
                    },
                },
            )
            assert propagated_06.status_code == 200, propagated_06.text
            propagated_profiles = (await client.get("/api/v1/profiles")).json()
            current_06_profiles = [
                profile
                for profile in propagated_profiles
                if Decimal(profile["nozzle_diameter_mm"]) == Decimal("0.6")
                and profile["filament_product_id"] in {product["id"], duplicated.json()["id"]}
            ]
            assert len(current_06_profiles) == 2
            assert {Decimal(profile["extruder_temp_c"]) for profile in current_06_profiles} == {
                Decimal("225")
            }
            assert {Decimal(profile["bed_temp_c"]) for profile in current_06_profiles} == {Decimal("72")}

            disabled_template = await client.patch(
                f"/api/v1/profiles/templates/{template_06['id']}",
                json={
                    "expected_version": propagated_06.json()["record_version"],
                    "active": False,
                },
            )
            assert disabled_template.status_code == 200, disabled_template.text
            inactive_scope = await client.post(
                "/api/v1/profiles/from-template",
                json={
                    "filament_product_id": product["id"],
                    "material_template_revision_id": propagated_06.json()["revisions"][0]["id"],
                },
            )
            assert inactive_scope.status_code == 422
            assert inactive_scope.json()["code"] == "material_template_inactive"

            # Drive the 0.4 scope above the 0.6 scope's version number, then
            # prove the legacy product-template compatibility path still
            # rebases the exact target scope instead of the global maximum.
            current_profiles = (await client.get("/api/v1/profiles")).json()
            current_04 = next(
                profile
                for profile in current_profiles
                if profile["filament_product_id"] == product["id"]
                and Decimal(profile["nozzle_diameter_mm"]) == Decimal("0.4")
            )
            current_06 = next(
                profile
                for profile in current_profiles
                if profile["filament_product_id"] == product["id"]
                and Decimal(profile["nozzle_diameter_mm"]) == Decimal("0.6")
            )
            while current_04["version"] <= current_06["version"]:
                current_04_response = await client.put(
                    f"/api/v1/profiles/{current_04['id']}/settings",
                    json={
                        "expected_profile_version": current_04["record_version"],
                        "settings": {
                            **{key: current_04[key] for key in MaterialSettingsInput.model_fields},
                            "extruder_temp_c": str(Decimal(current_04["extruder_temp_c"]) + Decimal("1")),
                        },
                    },
                )
                assert current_04_response.status_code == 200, current_04_response.text
                current_04 = current_04_response.json()

            # Cura-origin templates may coexist with a manual template in one
            # scope. Create that legitimate second identity directly because
            # the public create route intentionally creates manual templates.
            async with factory() as session:
                replacement_06_template = MaterialTemplate(
                    name="Template PLA imported",
                    material_type="PLA",
                    printer_id=printer.id,
                    nozzle_id=next(
                        nozzle.id for nozzle in physical_nozzles if nozzle.diameter_mm == Decimal("0.6")
                    ),
                    nozzle_diameter_mm=Decimal("0.6"),
                    filament_diameter_mm=Decimal("1.75"),
                    source_cura_material_id="replacement-pla-06",
                    active=True,
                )
                session.add(replacement_06_template)
                await session.flush()
                replacement_06_revision, _ = await save_template_settings(
                    session,
                    template=replacement_06_template,
                    settings={
                        **propagated_06.json()["revisions"][0]["settings"],
                        "extruder_temp_c": "230",
                    },
                    increment_template_record=False,
                )
                await session.commit()
                replacement_06_revision_id = str(replacement_06_revision.id)
            exact_scope_rebase = await client.patch(
                f"/api/v1/filaments/{product['id']}",
                json={
                    "expected_version": density_update.json()["record_version"],
                    "material_template_revision_id": replacement_06_revision_id,
                },
            )
            assert exact_scope_rebase.status_code == 200, exact_scope_rebase.text
            rebased_profiles = (await client.get("/api/v1/profiles")).json()
            rebased_04 = next(
                profile
                for profile in rebased_profiles
                if profile["filament_product_id"] == product["id"]
                and Decimal(profile["nozzle_diameter_mm"]) == Decimal("0.4")
            )
            rebased_06 = next(
                profile
                for profile in rebased_profiles
                if profile["filament_product_id"] == product["id"]
                and Decimal(profile["nozzle_diameter_mm"]) == Decimal("0.6")
            )
            assert rebased_04["id"] == current_04["id"]
            assert rebased_06["base_template_revision_id"] == replacement_06_revision_id
            assert Decimal(rebased_06["extruder_temp_c"]) == Decimal("230")

            # Updating the old, now-inactive template must not revive its
            # historical profile after the exact scope was rebased away.
            old_template_update = await client.put(
                f"/api/v1/profiles/templates/{template_06['id']}/settings",
                json={
                    "expected_template_version": disabled_template.json()["record_version"],
                    "settings": {
                        **propagated_06.json()["revisions"][0]["settings"],
                        "extruder_temp_c": "235",
                    },
                },
            )
            assert old_template_update.status_code == 200, old_template_update.text
            profiles_after_old_update = (await client.get("/api/v1/profiles")).json()
            current_after_old_update = next(
                profile
                for profile in profiles_after_old_update
                if profile["filament_product_id"] == product["id"]
                and Decimal(profile["nozzle_diameter_mm"]) == Decimal("0.6")
            )
            assert current_after_old_update["id"] == rebased_06["id"]
            assert current_after_old_update["base_template_revision_id"] == replacement_06_revision_id

        await engine.dispose()
