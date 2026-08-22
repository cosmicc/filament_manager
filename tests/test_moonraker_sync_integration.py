"""PostgreSQL-backed automatic Moonraker state synchronization tests."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.clients.moonraker import (
    MoonrakerBedMeshState,
    MoonrakerError,
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
    SpoolUsageEvent,
)
from filament_manager.models.operations import AuditEvent
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.services import events
from filament_manager.services.moonraker_sync import synchronize_active_spool
from filament_manager.services.print_history import synchronize_live_print, synchronize_print_history
from filament_manager.services.spool_preflight import build_spool_preflight_catalog
from filament_manager.workers import dispatcher


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
            draft_product = FilamentProduct(
                material_type="PLA",
                color_name="Orange",
                product_name="Draft profile filament",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
                source_template_revision_id=template_revision.id,
            )
            session.add(draft_product)
            await session.flush()
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
            third = Spool(
                spool_code="THIRD",
                filament_product_id=draft_product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("700"),
                remaining_mass_effective_g=Decimal("700"),
                status=SpoolStatus.IN_STOCK,
                spoolman_id=30,
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
            newer_draft_profile = MaterialProfile(
                filament_product_id=product.id,
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                version=2,
                status=ProfileStatus.DRAFT,
                extruder_temp_c=Decimal("218"),
                bed_temp_c=Decimal("60"),
                flow_percent=Decimal("100"),
                cooling_min_percent=Decimal("20"),
                cooling_max_percent=Decimal("100"),
                filament_density_g_cm3=Decimal("1.24"),
                base_template_revision_id=template_revision.id,
                setting_overrides={"extruder_temp_c": "218"},
            )
            draft_profile = MaterialProfile(
                filament_product_id=draft_product.id,
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                version=1,
                status=ProfileStatus.DRAFT,
                extruder_temp_c=Decimal("220"),
                bed_temp_c=Decimal("60"),
                flow_percent=Decimal("100"),
                cooling_min_percent=Decimal("20"),
                cooling_max_percent=Decimal("100"),
                filament_density_g_cm3=Decimal("1.24"),
                base_template_revision_id=template_revision.id,
                setting_overrides={"extruder_temp_c": "220"},
            )
            session.add_all([first, second, third, profile, newer_draft_profile, draft_profile])
            await session.commit()

            catalog = await build_spool_preflight_catalog(session, printer=printer)
            material_guid = cura_material_guid("product", profile.id)
            assert catalog.materials[material_guid] == [
                [10, "FIRST-Filament-Manager-PLA-Blue"],
                [20, "SECOND-Filament-Manager-PLA-Blue"],
            ]
            assert catalog.manual_spools == [
                [10, "FIRST-Filament-Manager-PLA-Blue"],
                [20, "SECOND-Filament-Manager-PLA-Blue"],
                [30, "THIRD-Filament-Manager-Draft-profile-filament-Orange"],
            ]
            assert catalog.print_temperatures == {"10": "215", "20": "215"}
            assert catalog.temperatures == {"10": "218", "20": "218", "30": "220"}

            prompted_targets: list[tuple[int, Decimal, str]] = []
            restored_spool_ids: list[int | None] = []

            class DirectSelectionClient:
                """Expose one direct Spoolman selection to the state reconciler."""

                def __init__(self, _configured: object) -> None:
                    pass

                async def active_spool_id(self) -> int:
                    return 20

                async def bed_mesh_state(self) -> MoonrakerBedMeshState:
                    return MoonrakerBedMeshState(profile_names=(), active_profile=None)

                async def spool_preflight_state(self) -> MoonrakerSpoolPreflightState:
                    return MoonrakerSpoolPreflightState(
                        restored=True,
                        initialized=True,
                        phase="idle",
                        loaded_spool_id=10,
                        catalog_revision=catalog.revision,
                        material_guid="",
                        start_bed_temp=Decimal("0"),
                        start_extruder_temp=Decimal("0"),
                        start_chamber_temp=Decimal("0"),
                        inspection_policy="warn",
                        start_pending=False,
                    )

                async def request_spoolman_target(
                    self, *, spoolman_id: int, temperature_c: Decimal, prompt_label: str
                ) -> dict[str, object]:
                    prompted_targets.append((spoolman_id, temperature_c, prompt_label))
                    return {"result": "ok"}

                async def set_active_spool(self, spoolman_id: int | None) -> dict[str, object]:
                    restored_spool_ids.append(spoolman_id)
                    return {"result": "ok"}

            monkeypatch.setattr(dispatcher, "get_settings", lambda: settings)
            monkeypatch.setattr(dispatcher, "MoonrakerClient", DirectSelectionClient)
            await dispatcher._reconcile_moonraker_state(
                session,
                SimpleNamespace(id=uuid4()),  # type: ignore[arg-type]
            )
            assert prompted_targets == [(20, Decimal("218"), "SECOND-Filament-Manager-PLA-Blue")]
            assert restored_spool_ids == [10]
            assert (await session.get(Spool, first.id)).active_printer_id == printer.id  # type: ignore[union-attr]
            assert (await session.get(Spool, second.id)).active_printer_id is None  # type: ignore[union-attr]

            class CatalogFailureClient(DirectSelectionClient):
                """Reject only the optional catalog write while other state remains usable."""

                async def spool_preflight_state(self) -> MoonrakerSpoolPreflightState:
                    return MoonrakerSpoolPreflightState(
                        restored=True,
                        initialized=True,
                        phase="idle",
                        loaded_spool_id=10,
                        catalog_revision="outdated",
                        material_guid="",
                        start_bed_temp=Decimal("0"),
                        start_extruder_temp=Decimal("0"),
                        start_chamber_temp=Decimal("0"),
                        inspection_policy="warn",
                        start_pending=False,
                    )

                async def synchronize_spool_preflight_catalog(
                    self, _catalog: object, *, inspection_policy: str
                ) -> dict[str, object]:
                    del inspection_policy
                    raise MoonrakerError("catalog rejected")

            monkeypatch.setattr(dispatcher, "MoonrakerClient", CatalogFailureClient)
            await dispatcher._reconcile_moonraker_state(
                session,
                SimpleNamespace(id=uuid4()),  # type: ignore[arg-type]
            )
            refreshed_printer = await session.get(Printer, printer.id)
            assert refreshed_printer is not None
            assert refreshed_printer.spool_preflight_status == "error"
            assert "save_variables" in (refreshed_printer.spool_preflight_message or "")
            baseline_audit_count = await session.scalar(select(func.count(AuditEvent.id)))

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
            assert await session.scalar(select(func.count(AuditEvent.id))) == baseline_audit_count + 1
            audit_event = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "spool.active.synchronize")
            )
            assert audit_event is not None and len(audit_event.correlation_id) == 64

            unchanged = await synchronize_active_spool(
                session,
                printer_id=printer.id,
                spoolman_id=20,
                actor_id=None,
                correlation_id="automatic-active-2",
            )
            assert unchanged.changed is False
            assert await session.scalar(select(func.count(AuditEvent.id))) == baseline_audit_count + 1

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
            assert await session.scalar(select(func.count(AuditEvent.id))) == baseline_audit_count + 2

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

                async def history_jobs(
                    self, *, start: int = 0, limit: int = 100, since: float | None = None
                ) -> tuple[dict[str, object], ...]:
                    del limit, since
                    if start:
                        return ()
                    return (
                        {
                            "job_id": "repeatable-history-id",
                            "filename": "repeatable.gcode",
                            "status": "completed",
                            "start_time": 1_777_000_000,
                            "end_time": 1_777_000_060,
                            "filament_used": 200,
                            "print_duration": 50,
                            "total_duration": 60,
                            "metadata": {},
                        },
                    )

                async def timelapse_files(self) -> tuple[dict[str, object], ...]:
                    return (
                        {
                            "path": "repeatable_2026-04-24.mp4",
                            "modified": 1_777_000_061,
                            "size": 1_048_576,
                        },
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
            repeat_job_id = await session.scalar(
                select(PrintJob.id).where(PrintJob.filename == "repeatable.gcode")
            )
            repeat_segment = await session.scalar(
                select(PrintMaterialSegment).where(PrintMaterialSegment.print_job_id == repeat_job_id)
            )
            assert repeat_segment is not None
            assert repeat_segment.actual_filament_weight_g is not None
            assert await session.scalar(select(func.count(SpoolUsageEvent.id))) == 1
            refreshed_second = await session.get(Spool, second.id)
            assert refreshed_second is not None
            assert refreshed_second.remaining_mass_effective_g == (
                Decimal("900") - repeat_segment.actual_filament_weight_g
            ).quantize(Decimal("0.001"))

            await synchronize_print_history(
                session,
                printer=printer,
                client=client,  # type: ignore[arg-type]
                correlation_id="history-after-live-completion",
            )
            repeated_job = await session.get(PrintJob, repeat_job_id)
            assert repeated_job is not None
            assert repeated_job.timelapse_url == "repeatable_2026-04-24.mp4"
            assert printer.last_print_history_sync_at is not None

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
            assert all(segment.actual_filament_weight_g is not None for segment in segments)
            second_spool_weight = segments[0].actual_filament_weight_g
            first_spool_weight = segments[1].actual_filament_weight_g
            assert second_spool_weight is not None and first_spool_weight is not None
            assert await session.scalar(select(func.count(SpoolUsageEvent.id))) == 3
            refreshed_first = await session.get(Spool, first.id)
            refreshed_second = await session.get(Spool, second.id)
            assert refreshed_first is not None and refreshed_second is not None
            assert refreshed_first.remaining_mass_effective_g == (
                Decimal("800") - first_spool_weight
            ).quantize(Decimal("0.001"))
            assert refreshed_second.remaining_mass_effective_g == (
                Decimal("900") - repeat_segment.actual_filament_weight_g - second_spool_weight
            ).quantize(Decimal("0.001"))

        await engine.dispose()
