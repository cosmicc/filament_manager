"""Real PostgreSQL regression for stale Cura feedback after template edits."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api.schemas import CuraManagedMaterialReport, MaterialSettingsInput
from filament_manager.domain.spool_preflight import cura_material_guid, cura_product_material_guid
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    Nozzle,
    Printer,
)
from filament_manager.models.workstations import WorkstationAgent
from filament_manager.services.cura_edits import import_managed_cura_edits
from filament_manager.services.material_settings import (
    create_published_profile_snapshot,
    save_template_settings,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_template_change_survives_stale_cura_reports_and_preserves_real_edits() -> None:
    """Projection drift cannot become ownership, including replayed no-op edits."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        engine = create_async_engine(postgres.get_connection_url())
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            administrator = User(
                username="test",
                normalized_username="test",
                display_name="Test",
                password_hash="test-only",
                role=UserRole.ADMINISTRATOR,
            )
            session.add(administrator)
            await session.flush()
            printer = Printer(
                printer_code="test",
                name="Test",
                moonraker_base_url="http://moonraker.test",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            product = FilamentProduct(
                material_type="PLA",
                product_name="PLA",
                color_name="Black",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            agent = WorkstationAgent(
                created_by=administrator.id,
                agent_code="test",
                display_name="Test",
                hostname="test",
                platform="arch_linux",
                architecture="x86_64",
                agent_version="0.7.4",
                token_hash="a" * 64,
                capabilities={},
                cura_installations=[],
                cura_materials=[],
            )
            session.add_all([printer, product, agent])
            await session.flush()
            nozzle = Nozzle(
                nozzle_code="test", printer_id=printer.id, diameter_mm=Decimal("0.4"), material="Brass"
            )
            session.add(nozzle)
            await session.flush()
            template = MaterialTemplate(
                name="Template PLA",
                material_type="PLA",
                printer_id=printer.id,
                nozzle_id=nozzle.id,
                nozzle_diameter_mm=Decimal("0.4"),
                filament_diameter_mm=Decimal("1.75"),
            )
            session.add(template)
            await session.flush()
            settings = MaterialSettingsInput(
                extruder_temp_c=210,
                bed_temp_c=60,
                flow_percent=100,
                cooling_min_percent=0,
                cooling_max_percent=100,
                filament_density_g_cm3=Decimal("1.24"),
                drying_temp_c=55,
                drying_time_hours="6-8",
                moisture_sensitivity="high",
            ).model_dump(mode="json")
            base, _ = await save_template_settings(session, template=template, settings=settings)
            original = await create_published_profile_snapshot(
                session,
                filament_product_id=product.id,
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                base_revision=base,
                settings={**settings, "bed_temp_c": "65", "drying_temp_c": "50"},
            )
            # A legacy redundant override is equal to its own base and must
            # be normalized before (not after) replacement of that base.
            original.setting_overrides = {**original.setting_overrides, "extruder_temp_c": "210.000"}
            await session.commit()

            def report(guid: str, edits: dict[str, str | bool] | None = None) -> CuraManagedMaterialReport:
                return CuraManagedMaterialReport(
                    source_id="b" * 64,
                    installation_id="test",
                    name="PLA",
                    brand="Unknown",
                    material_type="PLA",
                    color_name="Black",
                    material_guid=guid,
                    content_checksum="c" * 64,
                    settings={"material_print_temperature": "210", "material_flow": "100"},
                    **({"edited_settings": edits} if edits is not None else {}),
                )

            product_guid = cura_product_material_guid(product.id, printer.id, Decimal("0.4"))
            template_guid = cura_material_guid("template", template.id)

            async def ingest(reports: list[CuraManagedMaterialReport]) -> int:
                count = await import_managed_cura_edits(
                    session, agent=agent, reports=reports, correlation_id="test"
                )
                await session.commit()
                return count

            # An acknowledged no-op must remain consumed after the next save.
            no_op = report(product_guid, {"material_print_temperature": "210"})
            assert await ingest([no_op]) == 0
            _revision, profiles = await save_template_settings(
                session,
                template=template,
                settings={**settings, "extruder_temp_c": "220"},
            )
            await session.commit()
            inherited = profiles[0]
            assert inherited.extruder_temp_c == Decimal("220")
            assert "extruder_temp_c" not in inherited.setting_overrides
            assert inherited.bed_temp_c == Decimal("65")
            assert original.extruder_temp_c == Decimal("210")
            assert base.settings["extruder_temp_c"] == "210"
            assert await ingest([report(product_guid), report(template_guid), no_op]) == 0

            # Even explicit edits and legacy GUIDs are rejected: app-only.
            assert await ingest([report(product_guid, {"material_print_temperature": "225"})]) == 0
            assert await ingest([report(template_guid, {"material_print_temperature": "230"})]) == 0
            assert (
                await ingest([report(cura_material_guid("product", original.id), {"material_flow": "95"})])
                == 0
            )
            current = await session.scalar(
                select(MaterialProfile).order_by(MaterialProfile.version.desc()).limit(1)
            )
            assert current.id == inherited.id
            assert current.extruder_temp_c == Decimal("220")
            assert current.bed_temp_c == Decimal("65")
            assert current.drying_temp_c == Decimal("50")
        await engine.dispose()
