"""Canonical inventory summaries and post-use color corrections on PostgreSQL."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.api.routes import inventory, operations
from filament_manager.api.schemas import DashboardPrinterStateResponse
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import PrintJobStatus, SpoolStatus, UserRole
from filament_manager.models.inventory import FilamentColor, FilamentProduct, Printer, Spool
from filament_manager.models.operations import AuditEvent, OutboxJob
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.services import events


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inventory_summary_and_post_use_color_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Count physical inventory once and correct colors without rewriting evidence."""

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
            products = [
                FilamentProduct(
                    material_type=material,
                    color_name=color,
                    color_hex="FF0000",
                    color_hexes=["FF0000"],
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                )
                for material, color in [
                    ("PLA", "Red"),
                    ("pla", "RED"),
                    ("PLA+", "Blue"),
                    ("TPU", "Blue"),
                    ("PETG", "Green"),
                    ("ABS", "Purple"),
                ]
            ]
            session.add_all(
                [
                    user,
                    printer,
                    *products,
                    FilamentColor(
                        name="Red",
                        normalized_name="red",
                        color_hex="FF0000",
                        color_mode="solid",
                        color_hexes=["FF0000"],
                    ),
                ]
            )
            await session.flush()
            spools = [
                Spool(
                    spool_code=f"S{index}",
                    filament_product_id=product.id,
                    nominal_net_mass_g=Decimal("1000"),
                    tare_mass_g=Decimal("200"),
                    remaining_mass_expected_g=Decimal("100"),
                    remaining_mass_effective_g=Decimal("100"),
                    status=SpoolStatus.LOW,
                    archived=index == 4,
                )
                for index, product in enumerate(products[:5])
            ]
            session.add_all(spools)
            await session.flush()
            snapshot = {"product": {"color_name": "Red", "color_hex": "FF0000"}}
            job = PrintJob(
                printer_id=printer.id,
                spool_id=spools[0].id,
                filament_product_id=products[0].id,
                filename="retained.gcode",
                status=PrintJobStatus.COMPLETED,
                state_snapshot=snapshot,
                profile_snapshot={"flow_percent": "100"},
                print_settings_snapshot={"schema_version": 1, "color_name": "Red"},
            )
            session.add(job)
            await session.flush()
            segment = PrintMaterialSegment(
                print_job_id=job.id,
                segment_number=0,
                source="manual",
                created_at=datetime.now(UTC),
                spool_id=spools[1].id,
                filament_product_id=products[1].id,
                started_at=datetime.now(UTC),
                state_snapshot=snapshot,
            )
            session.add(segment)
            await session.commit()

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            return user

        async def unavailable_state(_: AsyncSession) -> DashboardPrinterStateResponse:
            return DashboardPrinterStateResponse(
                printer_name="Test Printer",
                connection_status="unavailable",
                operational_status="unavailable",
                klipper_state=None,
                print_state=None,
                filename=None,
                progress_percent=None,
                nozzle_temperature_c=None,
                nozzle_target_c=None,
                bed_temperature_c=None,
                bed_target_c=None,
                chamber_temperature_c=None,
                chamber_target_c=None,
                checked_at=datetime.now(UTC),
            )

        from filament_manager import config, main

        for module in (config, main, inventory, operations, events):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        monkeypatch.setattr(operations, "_dashboard_printer_state", unavailable_state)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        app.dependency_overrides[dependencies.current_user] = user_override
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            summary = await client.get("/api/v1/dashboard")
            assert summary.status_code == 200, summary.text
            assert summary.json()["total_spools"] == 4
            assert summary.json()["material_spool_counts"] == {"PLA": 2, "PLA+": 1, "TPU": 1}
            assert summary.json()["distinct_colors"] == 2
            assert summary.json()["low_spools"] == 4
            assert (await client.get(f"/api/v1/filaments/{products[0].id}")).json()["color_editable"] is True
            # Correct a shared swatch even when both products have retained print evidence.
            corrected = await client.patch(
                f"/api/v1/filaments/{products[0].id}", json={"expected_version": 1, "color_hex": "AA0000"}
            )
            assert corrected.status_code == 200, corrected.text
            for spool in spools[:2]:
                current = (await client.get(f"/api/v1/spools/{spool.id}")).json()
                assert current["color_hex"] == "AA0000"
                assert Decimal(current["remaining_mass_effective_g"]) == Decimal("100")
                assert current["spool_code"] == spool.spool_code
            renamed = await client.patch(
                f"/api/v1/filaments/{products[0].id}",
                json={
                    "expected_version": corrected.json()["record_version"],
                    "color_name": "Copper",
                    "color_hex": "AA6633",
                },
            )
            assert renamed.status_code == 200, renamed.text
            assert (await client.get(f"/api/v1/spools/{spools[0].id}")).json()["color_name"] == "Copper"
            assert (await client.get("/api/v1/dashboard")).json()["distinct_colors"] == 3
            conflict = await client.patch(
                f"/api/v1/filaments/{products[0].id}", json={"expected_version": 1, "color_name": "Stale"}
            )
            assert conflict.status_code == 409
            # Draft validation does not add a choice or overwrite a saved palette.
            draft = await client.post(
                "/api/v1/filament-colors",
                json={
                    "name": "Temporary",
                    "color_hex": "123456",
                },
            )
            assert draft.status_code == 200
            assert draft.json()["id"] is None
            choices = (await client.get("/api/v1/filament-colors")).json()
            assert "Temporary" not in {choice["name"] for choice in choices}
            assert "Rainbow" not in {choice["name"] for choice in choices}
            assert (
                await client.post(
                    "/api/v1/filament-colors",
                    json={
                        "name": "copper",
                        "color_hex": "FFFFFF",
                    },
                )
            ).status_code == 409
            rainbow = await client.post(
                "/api/v1/filament-colors",
                json={
                    "name": "Rainbow",
                    "color_hex": "123456",
                },
            )
            assert rainbow.status_code == 200 and len(rainbow.json()["color_hexes"]) == 6
            # Two and then three product-specific samples remain editable after use.
            for palette in (["112233", "445566"], ["778899", "AABBCC", "DDEEFF"]):
                renamed = await client.patch(
                    f"/api/v1/filaments/{products[0].id}",
                    json={
                        "expected_version": renamed.json()["record_version"],
                        "color_name": "Copper blend",
                        "color_mode": "multicolor",
                        "color_hexes": palette,
                        "finish": " None ",
                        "filler": "Glass",
                    },
                )
                assert renamed.status_code == 200, renamed.text
                assert renamed.json()["color_hexes"] == palette
                assert renamed.json()["finish"] == "Standard"
                assert (await client.get(f"/api/v1/spools/{spools[0].id}")).json()["color_hexes"] == palette
            choices = (await client.get("/api/v1/filament-colors")).json()
            assert "Copper" not in {choice["name"] for choice in choices}
            blend = next(choice for choice in choices if choice["name"] == "Copper blend")
            assert blend["color_mode"] == "multicolor" and blend["color_hexes"] == []
            assert (
                await client.post(
                    "/api/v1/filament-colors",
                    json={
                        "name": "Copper",
                        "color_hex": "AA6633",
                    },
                )
            ).status_code == 200
            # Archived products retain their choices; deleting an unused one does not.
            archived = await client.patch(
                f"/api/v1/filaments/{products[0].id}",
                json={
                    "expected_version": renamed.json()["record_version"],
                    "archived": True,
                },
            )
            assert archived.status_code == 200, archived.text
            assert "Glass" in {
                item["name"] for item in (await client.get("/api/v1/filament-attributes?kind=filler")).json()
            }
            assert "Copper blend" in {
                item["name"] for item in (await client.get("/api/v1/filament-colors")).json()
            }
            deleted = await client.delete(f"/api/v1/filaments/{products[5].id}")
            assert deleted.status_code == 200, deleted.text
            assert deleted.json()["disposition"] == "deleted"
            assert "Purple" not in {
                item["name"] for item in (await client.get("/api/v1/filament-colors")).json()
            }
            # Removing the last retained user's filler forgets the choice as well.
            cleared = await client.patch(
                f"/api/v1/filaments/{products[0].id}",
                json={
                    "expected_version": archived.json()["record_version"],
                    "filler": "None",
                },
            )
            assert cleared.status_code == 200, cleared.text
            assert "Glass" not in {
                item["name"] for item in (await client.get("/api/v1/filament-attributes?kind=filler")).json()
            }
        async with factory() as session:
            assert (
                await session.scalar(
                    select(FilamentColor.id).where(FilamentColor.normalized_name.in_(["copper", "temporary"]))
                )
                is None
            )
            retained = await session.get(PrintJob, job.id)
            retained_segment = await session.get(PrintMaterialSegment, segment.id)
            assert retained is not None and retained_segment is not None
            assert retained.state_snapshot == snapshot
            assert retained_segment.state_snapshot == snapshot
            assert retained.profile_snapshot == {"flow_percent": "100"}
            assert retained.print_settings_snapshot == {"schema_version": 1, "color_name": "Red"}
            jobs = list(
                await session.scalars(select(OutboxJob).where(OutboxJob.job_type == "spoolman.spool.upsert"))
            )
            assert {spools[0].id, spools[1].id} <= {queued.aggregate_id for queued in jobs}
            assert (
                await session.scalar(select(AuditEvent.id).where(AuditEvent.action == "filament.update"))
                is not None
            )
        await engine.dispose()
