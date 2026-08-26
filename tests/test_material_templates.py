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
from filament_manager.models.enums import NozzleStatus, ProfileStatus, UserRole
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    Nozzle,
    Printer,
)
from filament_manager.models.workstations import WorkstationAgent
from filament_manager.security import hash_password
from filament_manager.services.cura_library import build_cura_library


@pytest.mark.integration
@pytest.mark.asyncio
async def test_direct_template_save_updates_linked_product_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct saves cascade inherited values while retaining explicit overrides."""

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
            await session.flush()
            session.add(
                WorkstationAgent(
                    agent_code="paired-test-agent",
                    display_name="Paired Cura workstation",
                    hostname="cura-test",
                    platform="linux",
                    architecture="x86_64",
                    agent_version="0.5.3",
                    token_hash="a" * 64,
                    enabled=True,
                    cura_management_enabled=True,
                    created_by=administrator.id,
                )
            )
            nozzle = Nozzle(
                nozzle_code="NZ-040",
                printer_id=printer.id,
                diameter_mm=Decimal("0.4"),
                material="Brass",
                status=NozzleStatus.INSTALLED,
            )
            session.add(nozzle)
            await session.flush()
            printer.active_nozzle_id = nozzle.id
            await session.commit()
            printer_id = printer.id
            nozzle_id = nozzle.id

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
                    "nozzle_id": str(nozzle_id),
                    "nozzle_diameter_mm": "0.4",
                    "filament_diameter_mm": "1.75",
                    "settings": {
                        "extruder_temp_c": "245",
                        "bed_temp_c": "55",
                        "flow_percent": "100",
                        "cooling_enabled": True,
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "60",
                        "pressure_advance": "0.04",
                        "filament_density_g_cm3": "1.20",
                        "cura_extensions": {
                            "retraction_enable": True,
                            "cool_fan_speed_0": "0",
                            "acceleration_print": "4500",
                            "acceleration_infill": "5000",
                            "acceleration_wall": "3000",
                            "acceleration_roofing": "2500",
                            "acceleration_topbottom": "2800",
                            "acceleration_support": "3500",
                            "acceleration_travel": "7000",
                        },
                    },
                },
            )
            assert created.status_code == 201, created.text
            template = created.json()
            revision_id = template["revisions"][0]["id"]
            assert template["revisions"][0]["status"] == "published"
            second_template = await client.post(
                "/api/v1/profiles/templates",
                json={
                    "name": "Generic TPU",
                    "material_type": "TPU",
                    "printer_id": str(printer_id),
                    "nozzle_id": str(nozzle_id),
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
                    "filler": None,
                    "finish": "Silk",
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.21",
                    "nominal_net_mass_g": "500",
                    "material_template_revision_id": revision_id,
                },
            )
            assert product_response.status_code == 201, product_response.text
            product_id = product_response.json()["id"]
            spool_response = await client.post(
                "/api/v1/spools",
                json={
                    "spool_code": "PCTPE-001",
                    "filament_product_id": product_id,
                    "nominal_net_mass_g": "500",
                    "purchase_cost": "12.50",
                    "currency": "USD",
                },
            )
            assert spool_response.status_code == 201, spool_response.text
            assert Decimal(spool_response.json()["cost_per_gram"]) == Decimal("0.025000")

            product_profiles = await client.get("/api/v1/profiles")
            assert product_profiles.status_code == 200, product_profiles.text
            original_profile = next(
                item for item in product_profiles.json() if item["filament_product_id"] == product_id
            )
            assert original_profile["base_template_name"] == "Template PCTPE"
            assert original_profile["override_keys"] == ["filament_density_g_cm3"]
            assert original_profile["status"] == "published"

            templates = await client.get("/api/v1/profiles/templates?include_inactive=true")
            current_template = next(item for item in templates.json() if item["id"] == template["id"])
            invalid_save = await client.put(
                f"/api/v1/profiles/templates/{template['id']}/settings",
                json={
                    "expected_template_version": current_template["record_version"],
                    "settings": {
                        "extruder_temp_c": "250",
                        "bed_temp_c": "55",
                        "flow_percent": "0",
                        "cooling_enabled": True,
                        "cooling_min_percent": "101",
                        "cooling_max_percent": "50",
                        "support_overhang_angle_deg": "91",
                        "filament_density_g_cm3": "1.20",
                        "cura_extensions": {"klipper_smooth_time_factor": "0.5"},
                    },
                },
            )
            assert invalid_save.status_code == 422, invalid_save.text
            invalid_body = invalid_save.json()
            assert invalid_body["code"] == "validation_error"
            errors_by_field = {item["field"]: item["message"] for item in invalid_body["errors"]}
            assert "settings.flow_percent" in errors_by_field
            assert "settings.cooling_min_percent" in errors_by_field
            assert "settings.support_overhang_angle_deg" in errors_by_field
            assert "settings.cura_extensions.klipper_smooth_time_factor" in errors_by_field
            assert all("input" not in item for item in invalid_body["errors"])
            invalid_acceleration = await client.put(
                f"/api/v1/profiles/templates/{template['id']}/settings",
                json={
                    "expected_template_version": current_template["record_version"],
                    "settings": {
                        "chamber_temp_c": "40",
                        "extruder_temp_c": "250",
                        "bed_temp_c": "55",
                        "flow_percent": "100",
                        "print_speed_mm_s": "120",
                        "outer_wall_speed_mm_s": "60",
                        "inner_wall_speed_mm_s": "90",
                        "infill_speed_mm_s": "110",
                        "top_bottom_speed_mm_s": "70",
                        "initial_layer_speed_mm_s": "35",
                        "travel_speed_mm_s": "300",
                        "support_speed_mm_s": "80",
                        "retraction_distance_mm": "0.8",
                        "retraction_speed_mm_s": "45",
                        "retraction_prime_speed_mm_s": "40",
                        "cooling_enabled": True,
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "50",
                        "support_overhang_angle_deg": "55",
                        "tree_max_branch_angle_deg": "40",
                        "filament_density_g_cm3": "1.20",
                        "cura_extensions": {"acceleration_travel": "0"},
                    },
                },
            )
            assert invalid_acceleration.status_code == 422, invalid_acceleration.text
            acceleration_errors = {
                item["field"]: item["message"] for item in invalid_acceleration.json()["errors"]
            }
            assert "settings.cura_extensions.acceleration_travel" in acceleration_errors
            prefixed_extension_save = await client.put(
                f"/api/v1/profiles/templates/{template['id']}/settings",
                json={
                    "expected_template_version": current_template["record_version"],
                    "settings": {
                        "extruder_temp_c": "250",
                        "bed_temp_c": "55",
                        "flow_percent": "100",
                        "cooling_enabled": True,
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "50",
                        "filament_density_g_cm3": "1.20",
                        "cura_extensions": {"xy_offset_layer_0": "not-a-number"},
                    },
                },
            )
            assert prefixed_extension_save.status_code == 422, prefixed_extension_save.text
            prefixed_errors = {
                item["field"]: item["message"] for item in prefixed_extension_save.json()["errors"]
            }
            assert "settings.cura_extensions.xy_offset_layer_0" in prefixed_errors
            assert "settings.cura_extensions.xy_offset" not in prefixed_errors
            direct_save = await client.put(
                f"/api/v1/profiles/templates/{template['id']}/settings",
                json={
                    "expected_template_version": current_template["record_version"],
                    "settings": {
                        "chamber_temp_c": "40",
                        "extruder_temp_c": "250",
                        "bed_temp_c": "55",
                        "flow_percent": "100",
                        "print_speed_mm_s": "120",
                        "outer_wall_speed_mm_s": "60",
                        "inner_wall_speed_mm_s": "90",
                        "infill_speed_mm_s": "110",
                        "top_bottom_speed_mm_s": "70",
                        "initial_layer_speed_mm_s": "35",
                        "travel_speed_mm_s": "300",
                        "support_speed_mm_s": "80",
                        "retraction_distance_mm": "0.8",
                        "retraction_speed_mm_s": "45",
                        "retraction_prime_speed_mm_s": "40",
                        "cooling_enabled": True,
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "50",
                        "support_overhang_angle_deg": "55",
                        "tree_max_branch_angle_deg": "40",
                        "pressure_advance": "0.05",
                        "ironing_flow_percent": "12",
                        "ironing_speed_mm_s": "25",
                        "ironing_line_spacing_mm": "0.12",
                        "filament_density_g_cm3": "1.20",
                        "cura_extensions": {
                            "retraction_enable": True,
                            "retract_at_layer_change": True,
                            "cool_fan_speed_0": "15",
                            "cool_fan_full_layer": "4",
                            "cool_min_layer_time": "8",
                            "cool_min_layer_time_fan_speed_max": "20",
                            "cool_min_speed": "10",
                            "speed_roofing": "45",
                            "speed_travel_layer_0": "100",
                            "speed_wall": "70",
                            "skirt_brim_speed": "35",
                            "retraction_min_travel": "1.5",
                            "xy_offset_layer_0": "-0.1",
                            "xy_offset": "0.05",
                            "hole_xy_offset": "0.1",
                            "hole_xy_offset_max_diameter": "10",
                            "klipper_smooth_time_enable": True,
                            "klipper_smooth_time_factor": "0.04",
                            "acceleration_print": "5000",
                            "acceleration_infill": "5500",
                            "acceleration_wall": "3200",
                            "acceleration_roofing": "2600",
                            "acceleration_topbottom": "2900",
                            "acceleration_support": "3600",
                            "acceleration_travel": "8000",
                        },
                    },
                },
            )
            assert direct_save.status_code == 200, direct_save.text
            next_revision_id = direct_save.json()["revisions"][0]["id"]

            profiles_with_update = await client.get("/api/v1/profiles")
            inherited_profile = next(
                item for item in profiles_with_update.json() if item["filament_product_id"] == product_id
            )
            assert inherited_profile["id"] != original_profile["id"]
            assert inherited_profile["status"] == "published"
            assert inherited_profile["base_template_revision_id"] == next_revision_id
            assert inherited_profile["base_template_version"] == 2
            assert Decimal(inherited_profile["extruder_temp_c"]) == Decimal("250")
            assert Decimal(inherited_profile["filament_density_g_cm3"]) == Decimal("1.21")
            assert Decimal(inherited_profile["pressure_advance"]) == Decimal("0.05")
            assert Decimal(inherited_profile["ironing_flow_percent"]) == Decimal("12")
            assert Decimal(inherited_profile["ironing_speed_mm_s"]) == Decimal("25")
            assert Decimal(inherited_profile["ironing_line_spacing_mm"]) == Decimal("0.12")
            assert inherited_profile["cura_extensions"]["acceleration_travel"] == "8000"
            assert inherited_profile["override_keys"] == ["filament_density_g_cm3"]
            duplicate = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PCTPE",
                    "color_name": "Natural Copy",
                    "product_name": "Taulman PCTPE Copy",
                    "filler": None,
                    "finish": "Silk",
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.30",
                    "nominal_net_mass_g": "500",
                    "material_template_revision_id": next_revision_id,
                    "duplicate_source_filament_id": product_id,
                },
            )
            assert duplicate.status_code == 201, duplicate.text
            profiles_after_duplicate = await client.get("/api/v1/profiles")
            duplicate_profile = next(
                item
                for item in profiles_after_duplicate.json()
                if item["filament_product_id"] == duplicate.json()["id"]
            )
            assert duplicate_profile["override_keys"] == inherited_profile["override_keys"]
            assert Decimal(duplicate_profile["extruder_temp_c"]) == Decimal("250")
            assert Decimal(duplicate_profile["filament_density_g_cm3"]) == Decimal("1.30")
            exported = await client.get(f"/api/v1/profiles/{inherited_profile['id']}/exports/cura")
            assert exported.status_code == 200, exported.text
            assert exported.headers["content-disposition"].startswith(
                'attachment; filename="filament-manager-cura-profile-'
            )
            assert exported.headers["content-type"].startswith("application/json")
            assert exported.json()["cura"]["cool_fan_speed_0"] == "15"
            assert exported.json()["cura"]["acceleration_enabled"] is True
            assert exported.json()["cura"]["acceleration_travel_enabled"] is True
            assert exported.json()["cura"]["acceleration_print"] == "5000"
            assert exported.json()["cura"]["acceleration_infill"] == "5500"
            assert exported.json()["cura"]["acceleration_wall"] == "3200"
            assert exported.json()["cura"]["acceleration_roofing"] == "2600"
            assert exported.json()["cura"]["acceleration_topbottom"] == "2900"
            assert exported.json()["cura"]["acceleration_support"] == "3600"
            assert exported.json()["cura"]["acceleration_travel"] == "8000"
            assert Decimal(exported.json()["cura"]["ironing_flow"]) == Decimal("12")
            assert Decimal(exported.json()["cura"]["speed_ironing"]) == Decimal("25")
            assert Decimal(exported.json()["cura"]["ironing_line_spacing"]) == Decimal("0.12")

        async with factory() as session:
            template_row = await session.scalar(
                select(MaterialTemplate).where(MaterialTemplate.material_type == "PCTPE")
            )
            product = await session.get(FilamentProduct, product_id)
            profile = await session.scalar(
                select(MaterialProfile)
                .where(MaterialProfile.filament_product_id == product_id)
                .order_by(MaterialProfile.version.desc())
                .limit(1)
            )
            assert template_row is not None and template_row.material_type == "PCTPE"
            assert product is not None and product.source_template_revision_id is not None
            assert profile is not None
            assert profile.status == ProfileStatus.PUBLISHED
            assert profile.version == 2
            assert profile.base_template_revision_id == product.source_template_revision_id
            assert profile.extruder_temp_c == Decimal("250.00000")
            assert profile.filament_density_g_cm3 == Decimal("1.21000")
            assert profile.setting_overrides == {"filament_density_g_cm3": "1.21"}
            library = await build_cura_library(session)
            assert library["schema_version"] == 3
            materials = library["materials"]
            assert isinstance(materials, list) and len(materials) == 4
            product_material = next(
                item
                for item in materials
                if item["source_kind"] == "product" and item["material"]["product_id"] == product_id
            )
            assert product_material["material"]["filler"] is None
            assert product_material["material"]["finish"] == "Silk"
            assert product_material["material"]["cura_cost_basis"] == {
                "spool_weight_g": "1000",
                "spool_cost": "25.00",
                "currency": "USD",
                "source_spool_count": "1",
            }
            assert library["hide_bundled_materials"] is True
            assert "speed_print" in library["managed_material_setting_keys"]
            assert "speed_ironing" in library["managed_material_setting_keys"]
            assert "ironing_speed" not in library["managed_material_setting_keys"]
            assert "speed_print" in library["template_only_material_setting_keys"]
            assert "material_print_temperature" in library["editable_material_setting_keys"]
            assert "material_flow_layer_0" in library["retired_material_setting_keys"]
            assert "limit_support_retractions" not in library["managed_material_setting_keys"]
            assert "limit_support_retractions" in library["retired_material_setting_keys"]
            template_material = next(
                item
                for item in materials
                if item["source_kind"] == "template" and item["material"]["material_type"] == "PCTPE"
            )
            assert template_material["material"]["brand"] == "Template"
            assert template_material["material"]["product_name"] == "Template PCTPE"
            product_material = next(item for item in materials if item["source_kind"] == "product")
            assert product_material["material"]["brand"] == "Unknown"
            assert materials[0]["material"]["material_type"] == "PCTPE"

        await engine.dispose()
