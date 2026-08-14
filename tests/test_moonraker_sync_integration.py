"""PostgreSQL-backed automatic Moonraker state synchronization tests."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.clients.moonraker import (
    MoonrakerGcodeFile,
    MoonrakerPrintState,
    MoonrakerSpoolPreflightState,
)
from filament_manager.config import Settings
from filament_manager.domain.spool_preflight import cura_material_guid
from filament_manager.models import Base
from filament_manager.models.enums import ProfileStatus, SpoolStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Spool,
)
from filament_manager.models.operations import AuditEvent
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.services import events
from filament_manager.services.moonraker_sync import synchronize_active_spool
from filament_manager.services.print_history import synchronize_live_print
from filament_manager.services.spool_preflight import build_spool_preflight_catalog


def _settings(database_url: str) -> Settings:
    """Create complete settings for automatic connector mutations."""

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
async def test_active_spool_selection_and_clear_follow_moonraker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External selection atomically replaces and clears canonical active state."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = _settings(database_url)
        monkeypatch.setattr(events, "get_settings", lambda: settings)
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            printer = Printer(
                printer_code="test-printer",
                name="Test Printer",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            product = FilamentProduct(
                material_type="PLA",
                color_name="Blue",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add_all([printer, product])
            await session.flush()
            template = MaterialTemplate(
                name="Template PLA",
                material_type="PLA",
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                filament_diameter_mm=Decimal("1.75"),
            )
            session.add(template)
            await session.flush()
            template_revision = MaterialTemplateRevision(
                material_template_id=template.id,
                version=1,
                status=ProfileStatus.PUBLISHED,
                settings={
                    "extruder_temp_c": "215",
                    "bed_temp_c": "60",
                    "flow_percent": "100",
                    "cooling_enabled": True,
                    "cooling_min_percent": "20",
                    "cooling_max_percent": "100",
                    "filament_density_g_cm3": "1.24",
                    "cura_extensions": {},
                },
                published_at=datetime.now(UTC),
            )
            session.add(template_revision)
            await session.flush()
            product.source_template_revision_id = template_revision.id
            first = Spool(
                spool_code="FIRST",
                filament_product_id=product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("800"),
                remaining_mass_effective_g=Decimal("800"),
                status=SpoolStatus.IN_STOCK,
                spoolman_id=10,
                active_printer_id=printer.id,
            )
            second = Spool(
                spool_code="SECOND",
                filament_product_id=product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("900"),
                remaining_mass_effective_g=Decimal("900"),
                status=SpoolStatus.IN_STOCK,
                spoolman_id=20,
            )
            profile = MaterialProfile(
                filament_product_id=product.id,
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                version=1,
                status=ProfileStatus.PUBLISHED,
                extruder_temp_c=Decimal("215"),
                bed_temp_c=Decimal("60"),
                flow_percent=Decimal("100"),
                cooling_min_percent=Decimal("20"),
                cooling_max_percent=Decimal("100"),
                filament_density_g_cm3=Decimal("1.24"),
                base_template_revision_id=template_revision.id,
                setting_overrides={},
            )
            session.add_all([first, second, profile])
            await session.commit()

            catalog = await build_spool_preflight_catalog(session, printer=printer)
            material_guid = cura_material_guid("product", profile.id)
            assert catalog.materials[material_guid] == [
                [10, "FIRST-Filament-Manager-PLA-Blue"],
                [20, "SECOND-Filament-Manager-PLA-Blue"],
            ]
            assert catalog.temperatures == {"10": "215", "20": "215"}

            selected = await synchronize_active_spool(
                session,
                printer_id=printer.id,
                spoolman_id=20,
                actor_id=None,
                correlation_id=f"automatic:{'worker-context-' * 8}:active-spool",
            )
            assert selected.changed is True
            assert selected.active_spool_id == second.id
            assert (await session.get(Spool, first.id)).active_printer_id is None  # type: ignore[union-attr]
            assert (await session.get(Spool, second.id)).active_printer_id == printer.id  # type: ignore[union-attr]
            assert await session.scalar(select(func.count(AuditEvent.id))) == 1
            audit_event = await session.scalar(select(AuditEvent))
            assert audit_event is not None and len(audit_event.correlation_id) == 64

            unchanged = await synchronize_active_spool(
                session,
                printer_id=printer.id,
                spoolman_id=20,
                actor_id=None,
                correlation_id="automatic-active-2",
            )
            assert unchanged.changed is False
            assert await session.scalar(select(func.count(AuditEvent.id))) == 1

            cleared = await synchronize_active_spool(
                session,
                printer_id=printer.id,
                spoolman_id=None,
                actor_id=None,
                correlation_id="automatic-active-3",
            )
            assert cleared.changed is True
            assert cleared.active_spool_id is None
            assert (await session.get(Spool, second.id)).active_printer_id is None  # type: ignore[union-attr]
            assert await session.scalar(select(func.count(AuditEvent.id))) == 2

            class InspectionClient:
                """Provide one bounded file without an external Moonraker dependency."""

                async def gcode_metadata(self, filename: str) -> dict[str, object]:
                    assert filename in {"repeatable.gcode", "material-change.gcode"}
                    return {"slicer": "Cura", "filament_total": 1000}

                async def gcode_file(self, filename: str) -> MoonrakerGcodeFile:
                    assert filename in {"repeatable.gcode", "material-change.gcode"}
                    return MoonrakerGcodeFile(
                        sha256="a" * 64,
                        header=f";Generated with Cura_SteamEngine 5.10\nMATERIAL_GUID={material_guid}\n",
                        tail="",
                        size=96,
                    )

            preflight = MoonrakerSpoolPreflightState(
                restored=True,
                initialized=True,
                phase="idle",
                loaded_spool_id=20,
                catalog_revision="b" * 64,
                material_guid=material_guid,
                start_bed_temp=Decimal("60"),
                start_extruder_temp=Decimal("215"),
                start_chamber_temp=Decimal("0"),
                inspection_policy="warn",
                start_pending=False,
            )
            printing = MoonrakerPrintState(
                filename="repeatable.gcode",
                state="printing",
                message=None,
                total_duration=Decimal("30"),
                print_duration=Decimal("25"),
                filament_used_mm=Decimal("100"),
            )
            completed = MoonrakerPrintState(
                filename="repeatable.gcode",
                state="complete",
                message=None,
                total_duration=Decimal("60"),
                print_duration=Decimal("50"),
                filament_used_mm=Decimal("200"),
            )
            client = InspectionClient()
            await synchronize_live_print(
                session,
                printer=printer,
                client=client,  # type: ignore[arg-type]
                print_state=printing,
                preflight_state=preflight,
                correlation_id="terminal-poll-1",
            )
            await synchronize_live_print(
                session,
                printer=printer,
                client=client,  # type: ignore[arg-type]
                print_state=completed,
                preflight_state=preflight,
                correlation_id="terminal-poll-2",
            )
            await synchronize_live_print(
                session,
                printer=printer,
                client=client,  # type: ignore[arg-type]
                print_state=completed,
                preflight_state=preflight,
                correlation_id="terminal-poll-3",
            )
            assert await session.scalar(select(func.count(PrintJob.id))) == 1

            material_change_start = MoonrakerPrintState(
                filename="material-change.gcode",
                state="printing",
                message=None,
                total_duration=Decimal("30"),
                print_duration=Decimal("25"),
                filament_used_mm=Decimal("100"),
            )
            changed_preflight = MoonrakerSpoolPreflightState(
                restored=True,
                initialized=True,
                phase="idle",
                loaded_spool_id=10,
                catalog_revision="b" * 64,
                material_guid=material_guid,
                start_bed_temp=Decimal("60"),
                start_extruder_temp=Decimal("215"),
                start_chamber_temp=Decimal("0"),
                inspection_policy="warn",
                start_pending=False,
            )
            after_change = MoonrakerPrintState(
                filename="material-change.gcode",
                state="printing",
                message=None,
                total_duration=Decimal("60"),
                print_duration=Decimal("50"),
                filament_used_mm=Decimal("150"),
            )
            material_change_complete = MoonrakerPrintState(
                filename="material-change.gcode",
                state="complete",
                message=None,
                total_duration=Decimal("90"),
                print_duration=Decimal("75"),
                filament_used_mm=Decimal("200"),
            )
            await synchronize_live_print(
                session,
                printer=printer,
                client=client,  # type: ignore[arg-type]
                print_state=material_change_start,
                preflight_state=preflight,
                correlation_id="material-change-1",
            )
            await synchronize_live_print(
                session,
                printer=printer,
                client=client,  # type: ignore[arg-type]
                print_state=after_change,
                preflight_state=changed_preflight,
                correlation_id="material-change-2",
            )
            await synchronize_live_print(
                session,
                printer=printer,
                client=client,  # type: ignore[arg-type]
                print_state=material_change_complete,
                preflight_state=changed_preflight,
                correlation_id="material-change-3",
            )
            material_change_job_id = await session.scalar(
                select(PrintJob.id).where(PrintJob.filename == "material-change.gcode")
            )
            segments = list(
                await session.scalars(
                    select(PrintMaterialSegment)
                    .where(PrintMaterialSegment.print_job_id == material_change_job_id)
                    .order_by(PrintMaterialSegment.segment_number)
                )
            )
            assert [segment.spool_id for segment in segments] == [second.id, first.id]
            assert [segment.actual_filament_length_mm for segment in segments] == [
                Decimal("150"),
                Decimal("50"),
            ]
            assert all(segment.ended_at is not None for segment in segments)

        await engine.dispose()
