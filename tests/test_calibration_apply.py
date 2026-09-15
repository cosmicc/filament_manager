"""Real PostgreSQL proof that reviewed calibration saves replace template defaults."""

from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager import config, main
from filament_manager.api import dependencies
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.calibration import CalibrationSession, CalibrationStep
from filament_manager.models.enums import CalibrationStatus, CalibrationStepStatus, UserRole
from filament_manager.models.inventory import (
    BuildPlateSurface,
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
)
from filament_manager.services import events
from filament_manager.services.material_settings import (
    create_published_profile_snapshot,
    save_template_settings,
)
from filament_manager.services.seed import DEFAULT_ASA_SETTINGS, seed_configured_system


@pytest.mark.integration
@pytest.mark.asyncio
async def test_calibration_template_save_persists_and_cascades(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Overwrite reviewed values, retain other settings/overrides/history, reject repeat saves."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        settings = integration_settings(postgres.get_connection_url(), tmp_path)
        engine = create_async_engine(postgres.get_connection_url())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        for module in (config, main, events):
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
                session,
                template=template,
                settings={
                    **DEFAULT_ASA_SETTINGS,
                    "extruder_temp_c": "210",
                    "drying_temp_c": "45",
                    "cura_extensions": {"xy_offset": "0.1", "hole_xy_offset": "0.1"},
                },
            )
            products = []
            profiles = []
            for index in range(3):
                product = FilamentProduct(
                    product_name=f"PLA {index}",
                    material_type="PLA",
                    color_name="Blue",
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                    source_template_revision_id=revision.id,
                )
                session.add(product)
                await session.flush()
                profile = await create_published_profile_snapshot(
                    session,
                    filament_product_id=product.id,
                    printer_id=printer.id,
                    nozzle_diameter_mm=printer.nozzle_diameter_mm,
                    base_revision=revision,
                    settings={**revision.settings, **({"extruder_temp_c": "230"} if index == 2 else {})},
                )
                products.append(product)
                profiles.append(profile)
            calibration = CalibrationSession(
                filament_product_id=products[0].id,
                printer_id=printer.id,
                nozzle_diameter_mm=printer.nozzle_diameter_mm,
                baseline_profile_id=profiles[0].id,
                build_plate_surface_id=side.id,
                status=CalibrationStatus.READY_TO_PUBLISH,
                operator_id=user.id,
            )
            session.add(calibration)
            await session.flush()
            session.add(
                CalibrationStep(
                    session_id=calibration.id,
                    step_order=1,
                    step_key="temperature",
                    name="Temperature Tower",
                    required=True,
                    status=CalibrationStepStatus.COMPLETED,
                    result={
                        "extruder_temp_c": "220",
                        "bed_temp_c": "60",
                        "flow_percent": "97.5",
                        "retraction_distance_mm": "2",
                        "retraction_speed_mm_s": "25",
                        "retraction_prime_speed_mm_s": "30",
                        "support_overhang_angle_deg": "55",
                        "tree_max_branch_angle_deg": "45",
                        "pressure_advance": "0.04",
                        "xy_offset": "-0.075",
                        "hole_xy_offset": "0.2",
                        "ironing_flow_percent": "12",
                    },
                )
            )
            # A later unrelated template edit must survive application of this older calibration.
            await save_template_settings(
                session, template=template, settings={**revision.settings, "drying_temp_c": "50"}
            )
            await session.commit()
            calibration_id, template_id, original_revision_id = calibration.id, template.id, revision.id
            original_profile_ids = [profile.id for profile in profiles]
            product_ids = [product.id for product in products]

        async def sessions() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = sessions
        app.dependency_overrides[dependencies.current_user] = lambda: user
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as client:
            preview = await client.get(f"/api/v1/calibrations/{calibration_id}/suggestions")
            assert preview.status_code == 200, preview.text
            assert "preferred_build_plate_surface_id" not in preview.json()["suggestions"]
            payload = {"expected_version": 1, "confirm_template_name": template.name}
            wrong = await client.post(
                f"/api/v1/calibrations/{calibration_id}/apply-template-settings",
                json={**payload, "confirm_template_name": "Wrong"},
            )
            assert wrong.status_code == 422
            response = await client.post(
                f"/api/v1/calibrations/{calibration_id}/apply-template-settings", json=payload
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "published"
            repeated = await client.post(
                f"/api/v1/calibrations/{calibration_id}/apply-template-settings", json=payload
            )
            assert repeated.status_code == 409
            current = await client.get("/api/v1/profiles/templates")
            saved_template = next(item for item in current.json() if item["id"] == str(template_id))
            saved = max(saved_template["revisions"], key=lambda item: item["version"])["settings"]
            assert Decimal(saved["extruder_temp_c"]) == Decimal("220")
            assert Decimal(saved["flow_percent"]) == Decimal("97.5")
            assert Decimal(saved["drying_temp_c"]) == Decimal("50")
            assert Decimal(saved["ironing_flow_percent"]) == Decimal("12")
            assert Decimal(saved["cura_extensions"]["xy_offset"]) == Decimal("-0.075")
            assert Decimal(saved["cura_extensions"]["hole_xy_offset"]) == Decimal("0.2")
            assert saved["preferred_build_plate_surface_id"] is None

        async with factory() as session:
            applied = await session.get(CalibrationSession, calibration_id)
            assert applied and applied.published_profile_id and applied.completed_at
            for index, product_id in enumerate(product_ids):
                profile = await session.scalar(
                    select(MaterialProfile)
                    .where(MaterialProfile.filament_product_id == product_id)
                    .order_by(MaterialProfile.version.desc())
                    .limit(1)
                )
                assert profile and profile.extruder_temp_c == Decimal("230" if index == 2 else "220")
                assert profile.flow_percent == Decimal("97.5")
            original = await session.get(MaterialTemplateRevision, original_revision_id)
            assert original and Decimal(str(original.settings["extruder_temp_c"])) == Decimal("210")
            old_profile = await session.get(MaterialProfile, original_profile_ids[0])
            assert old_profile and old_profile.extruder_temp_c == Decimal("210")
        await engine.dispose()
