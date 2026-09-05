"""Version 0.7.1 canonical weight, manufacturer suggestion, and location contracts."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.api.routes import inventory
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import JobStatus, PrintJobStatus, UserRole
from filament_manager.models.inventory import (
    FilamentProduct,
    Printer,
    Spool,
    SpoolLocationChoice,
    SpoolMeasurement,
    SpoolUsageEvent,
    Vendor,
)
from filament_manager.models.operations import AuditEvent, OutboxJob
from filament_manager.models.printing import PrintJob, PrintMaterialSegment
from filament_manager.services import events
from filament_manager.services.print_history import _apply_terminal_spool_usage
from filament_manager.services.spool_mass import SpoolMassBasis
from filament_manager.workers import dispatcher


def test_mass_basis_keeps_usage_and_clamps_exhausted_inventory() -> None:
    """Tare is re-evaluated, not added to the retained consumption ledger."""

    basis = SpoolMassBasis(Decimal("1200"), Decimal("-125"))
    assert basis.remaining(Decimal("250")) == Decimal("825")
    assert basis.remaining(Decimal("225")) == Decimal("850")
    assert SpoolMassBasis(Decimal("400"), Decimal("-300")).remaining(Decimal("200")) == 0
    with pytest.raises(ValueError, match="cannot exceed"):
        basis.remaining(Decimal("1201"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tare_edits_preserve_usage_and_location_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise real HTTP query parsing, atomic corrections, and immutable evidence."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = integration_settings(database_url)
        engine = create_async_engine(database_url)
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
            vendor = Vendor(name="Shared manufacturer")
            other_vendor = Vendor(name="Other manufacturer")
            session.add_all([user, vendor, other_vendor])
            await session.flush()
            products = [
                FilamentProduct(
                    vendor_id=owner,
                    material_type=material,
                    color_name="Blue",
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                )
                for owner, material in [
                    (vendor.id, "PLA"),
                    (vendor.id, "PETG"),
                    (other_vendor.id, "ASA"),
                    (None, "TPU"),
                ]
            ]
            session.add_all(products)
            await session.commit()
            product_ids = [str(product.id) for product in products]

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            return user

        from filament_manager import config, main

        for module in (config, main, inventory, events, dispatcher):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        app.dependency_overrides[dependencies.current_user] = user_override
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:

            async def create(code: str, product: str, **extra: object) -> dict:
                response = await client.post(
                    "/api/v1/spools",
                    json={
                        "spool_code": code,
                        "filament_product_id": product,
                        "nominal_net_mass_g": "1000",
                        **extra,
                    },
                )
                assert response.status_code == 201, response.text
                return response.json()

            spool = await create(
                "WEIGHED", product_ids[0], initial_gross_mass_g="1200", location="Bucket %_12"
            )
            spool_id = UUID(spool["id"])
            assert spool["vendor_name"] == "Shared manufacturer"
            assert Decimal(spool["current_total_mass_g"]) == 1200
            assert Decimal(spool["tare_mass_g"]) == 200
            stored = (await client.get(f"/api/v1/spools/{spool_id}")).json()
            assert stored["id"] == spool["id"] and stored["vendor_name"] == spool["vendor_name"]
            for key in (
                "tare_mass_g",
                "nominal_net_mass_g",
                "remaining_mass_effective_g",
                "current_total_mass_g",
            ):
                assert Decimal(stored[key]) == Decimal(spool[key])
            async with factory() as session:
                assert await session.scalar(select(func.count(SpoolMeasurement.id))) == 1
                initial = await session.scalar(select(SpoolMeasurement))
                assert initial is not None and initial.gross_mass_g == 1200
                counts = [
                    await session.scalar(select(func.count(model.id)))
                    for model in (Spool, SpoolMeasurement, AuditEvent, OutboxJob, SpoolLocationChoice)
                ]

            async def fail_response(*args: object, **kwargs: object) -> None:
                raise RuntimeError("Synthetic response validation failure")

            # The former commit-before-response path saved a spool despite a 500.
            # Every write, including its measurement and projection, must roll back.
            with monkeypatch.context() as patcher:
                patcher.setattr(inventory, "spool_response_with_statistics", fail_response)
                patcher.setattr(main, "logger", Mock())
                failed = await client.post(
                    "/api/v1/spools",
                    json={
                        "spool_code": "RESPONSE-FAILURE",
                        "filament_product_id": product_ids[0],
                        "nominal_net_mass_g": "1000",
                        "initial_gross_mass_g": "1200",
                        "location": "Rolled back",
                    },
                )
                assert failed.status_code == 500
                assert failed.json()["message"] == "The request could not be completed"
            async with factory() as session:
                assert [
                    await session.scalar(select(func.count(model.id)))
                    for model in (Spool, SpoolMeasurement, AuditEvent, OutboxJob, SpoolLocationChoice)
                ] == counts
            assert (await client.get("/api/v1/spool-location-choices")).json() == [{"name": "Bucket %_12"}]
            user.role = UserRole.VIEWER
            assert (await client.get("/api/v1/spool-location-choices")).status_code == 200
            assert (
                await client.post("/api/v1/spool-location-choices", json={"name": "Forbidden"})
            ).status_code == 403
            user.role = UserRole.ADMINISTRATOR
            for name in ("  Unused shelf  ", "Unused shelf", "unused shelf"):
                result = await client.post("/api/v1/spool-location-choices", json={"name": name})
                assert result.status_code == 201, result.text
            assert (await client.get("/api/v1/spool-location-choices")).json() == [
                {"name": "Bucket %_12"},
                {"name": "Unused shelf"},
                {"name": "unused shelf"},
            ]
            for name in ("  ", "x" * 161):
                assert (
                    await client.post("/api/v1/spool-location-choices", json={"name": name})
                ).status_code == 422
            async with factory() as session:
                assert (
                    await session.scalar(
                        select(func.count(AuditEvent.id)).where(
                            AuditEvent.action == "spool_location_choice.create"
                        )
                    )
                    == 2
                )
            async with factory() as session:
                row = await session.get(Spool, spool_id)
                assert row is not None
                row.spoolman_id = 7
                row.remaining_mass_effective_g = row.remaining_mass_expected_g = Decimal("875")
                now = datetime.now(UTC)
                session.add(
                    SpoolUsageEvent(
                        spool_id=spool_id,
                        source="spoolman",
                        mass_delta_g=Decimal("-125"),
                        idempotency_key="initial-use",
                        occurred_at=now,
                        created_at=now,
                    )
                )
                await session.commit()

            async def patch(**changes: object) -> dict:
                nonlocal spool
                response = await client.patch(
                    f"/api/v1/spools/{spool_id}",
                    json={"expected_version": spool["record_version"], **changes},
                )
                assert response.status_code == 200, response.text
                spool = response.json()
                return spool

            assert Decimal((await patch(tare_mass_g="250"))["remaining_mass_effective_g"]) == 825
            assert Decimal(spool["current_total_mass_g"]) == 1075
            assert Decimal((await patch(tare_mass_g="225"))["remaining_mass_effective_g"]) == 850
            assert (
                Decimal((await patch(notes="No additional weight change"))["remaining_mass_effective_g"])
                == 850
            )
            assert Decimal((await patch(remaining_mass_g="840"))["remaining_mass_effective_g"]) == 840
            assert Decimal((await patch(tare_mass_g="235"))["remaining_mass_effective_g"]) == 830
            basis = (await client.get(f"/api/v1/spools/{spool_id}/mass-basis")).json()
            assert Decimal(basis["last_gross_mass_g"]) == 1200
            assert Decimal(basis["adjustment_since_weighing_g"]) == -135
            async with factory() as session:
                measurement = await session.scalar(
                    select(SpoolMeasurement).where(SpoolMeasurement.spool_id == spool_id)
                )
                assert measurement is not None
                assert (
                    measurement.gross_mass_g == 1200
                    and measurement.tare_mass_g == 200
                    and measurement.net_mass_g == 1000
                )
                assert (
                    await session.scalar(
                        select(func.count(SpoolUsageEvent.id)).where(
                            SpoolUsageEvent.spool_id == spool_id, SpoolUsageEvent.source == "tare_correction"
                        )
                    )
                    == 3
                )
                assert await session.scalar(
                    select(OutboxJob.id)
                    .where(
                        OutboxJob.job_type == "spoolman.spool.adjust_weight",
                        OutboxJob.aggregate_id == spool_id,
                    )
                    .limit(1)
                )

            measured = await client.post(
                f"/api/v1/spools/{spool_id}/measurements",
                headers={"Idempotency-Key": "new-physical-baseline"},
                json={"gross_mass_g": "1000", "confirmed": True},
            )
            assert measured.status_code == 201, measured.text
            spool = (await client.get(f"/api/v1/spools/{spool_id}")).json()
            assert Decimal((await patch(tare_mass_g="240"))["remaining_mass_effective_g"]) == 760
            rejected = await client.patch(
                f"/api/v1/spools/{spool_id}",
                json={"expected_version": spool["record_version"], "tare_mass_g": "1001"},
            )
            assert rejected.status_code == 422
            assert (
                await client.patch(
                    f"/api/v1/spools/{spool_id}", json={"expected_version": 1, "tare_mass_g": "100"}
                )
            ).status_code == 409

            class Remote:
                async def list_spools(self) -> list[dict[str, object]]:
                    return [
                        {
                            "id": 7,
                            "remaining_weight": "700",
                            "location": "Bucket %_12",
                            "extra": {"filament_manager_spool_uuid": f'"{spool_id}"'},
                        }
                    ]

            async with factory() as session:
                await dispatcher._reconcile_spoolman(session, Remote())  # type: ignore[arg-type]
                await session.commit()
                row = await session.get(Spool, spool_id)
                assert row is not None and row.remaining_mass_effective_g == 760
                await session.execute(
                    update(OutboxJob)
                    .where(OutboxJob.job_type == "spoolman.spool.adjust_weight")
                    .values(status=JobStatus.COMPLETED)
                )
                oldest_correction = await session.scalar(
                    select(OutboxJob)
                    .where(OutboxJob.job_type == "spoolman.spool.adjust_weight")
                    .order_by(OutboxJob.aggregate_version)
                    .limit(1)
                )
                assert oldest_correction is not None
                oldest_correction.status = JobStatus.FAILED
                await session.commit()
                await dispatcher._reconcile_spoolman(session, Remote())  # type: ignore[arg-type]
                await session.commit()
            spool = (await client.get(f"/api/v1/spools/{spool_id}")).json()
            assert Decimal(spool["remaining_mass_effective_g"]) == 700
            assert Decimal((await patch(tare_mass_g="220"))["remaining_mass_effective_g"]) == 720

            unweighed = await create("UNWEIGHED", product_ids[0], tare_mass_g="200", location="Bucket XX12")
            response = await client.patch(
                f"/api/v1/spools/{unweighed['id']}", json={"expected_version": 1, "tare_mass_g": "220"}
            )
            assert Decimal(response.json()["remaining_mass_effective_g"]) == 1000
            archived = await create("ARCHIVED", product_ids[1], tare_mass_g="100", nominal_net_mass_g="500")
            assert (
                await client.patch(
                    f"/api/v1/spools/{archived['id']}", json={"expected_version": 1, "archived": True}
                )
            ).status_code == 200
            await create("OTHER", product_ids[2], tare_mass_g="999")
            suggestions = (
                await client.get(
                    "/api/v1/spool-tare-suggestions", params={"filament_product_id": product_ids[1]}
                )
            ).json()
            assert [(Decimal(item["tare_mass_g"]), item["spool_count"]) for item in suggestions] == [
                (Decimal("220"), 2),
                (Decimal("100"), 1),
            ]
            assert (
                await client.get(
                    "/api/v1/spool-tare-suggestions", params={"filament_product_id": product_ids[3]}
                )
            ).json() == []
            locations = (await client.get("/api/v1/locations")).json()
            assert len(locations) == 3
            exact = (await client.get("/api/v1/spools", params={"location_exact": "Bucket %_12"})).json()
            assert exact["total"] == 1 and exact["items"][0]["id"] == str(spool_id)
            assert (await client.get("/api/v1/spools?unassigned=true")).json()["total"] == 1
            assert (await client.get("/api/v1/spools?unassigned=true&include_archived=true")).json()[
                "total"
            ] == 2
            assert (await client.get("/api/v1/spools?material=pla")).json()["total"] == 2
            assert len((await client.get("/api/v1/filaments?material=petg")).json()) == 1

            rejected_used = await client.post(
                "/api/v1/spools",
                json={
                    "spool_code": "USED-UNKNOWN",
                    "filament_product_id": product_ids[0],
                    "nominal_net_mass_g": "1000",
                    "initial_gross_mass_g": "700",
                    "infer_tare_from_unused_spool": False,
                },
            )
            assert rejected_used.status_code == 422
            used = await create(
                "USED-KNOWN",
                product_ids[0],
                initial_gross_mass_g="700",
                tare_mass_g="250",
                infer_tare_from_unused_spool=False,
            )
            assert Decimal(used["remaining_mass_effective_g"]) == 450

            async with factory() as session:
                session.add_all(
                    [
                        Spool(
                            spool_code=f"LARGE-LOCATION-{index:03}",
                            filament_product_id=UUID(product_ids[0]),
                            nominal_net_mass_g=Decimal("1000"),
                            remaining_mass_effective_g=Decimal("500"),
                            remaining_mass_expected_g=Decimal("500"),
                            location="Large location",
                        )
                        for index in range(205)
                    ]
                )
                await session.commit()
            final_page = (
                await client.get("/api/v1/spools?location_exact=Large%20location&limit=50&offset=200")
            ).json()
            assert final_page["total"] == 205 and len(final_page["items"]) == 5

            # A tare correction already present in an M600 snapshot must not
            # be applied twice; a later correction must change the usage target.
            async with factory() as session:
                printer = Printer(
                    printer_code="weight-test",
                    name="Weight test",
                    moonraker_base_url="http://moonraker.test:7125",
                    nozzle_diameter_mm=Decimal("0.4"),
                )
                session.add(printer)
                await session.flush()
                captured = datetime.now(UTC)
                row = await session.get(Spool, UUID(used["id"]))
                assert row is not None
                row.remaining_mass_effective_g = row.remaining_mass_expected_g = Decimal("425")
                row.tare_mass_g = Decimal("275")
                for seconds, delta in [(-1, "50"), (1, "-25")]:
                    session.add(
                        SpoolUsageEvent(
                            spool_id=row.id,
                            source="tare_correction",
                            mass_delta_g=Decimal(delta),
                            idempotency_key=f"print-tare-{seconds}",
                            occurred_at=captured + timedelta(seconds=seconds),
                            created_at=captured + timedelta(seconds=seconds),
                        )
                    )
                job = PrintJob(
                    printer_id=printer.id,
                    filename="tare-test.gcode",
                    source="live",
                    status=PrintJobStatus.COMPLETED,
                    started_at=captured - timedelta(minutes=10),
                    ended_at=captured + timedelta(seconds=10),
                    segments=[
                        PrintMaterialSegment(
                            segment_number=2,
                            spool_id=row.id,
                            source="m600",
                            state_snapshot={"spool": {"remaining_mass_g": "450"}},
                            started_at=captured - timedelta(seconds=2),
                            created_at=captured,
                            actual_filament_weight_g=Decimal("100"),
                        )
                    ],
                )
                session.add(job)
                await session.flush()
                await _apply_terminal_spool_usage(session, job=job, correlation_id="tare-terminal")
                await session.flush()
                assert row.remaining_mass_effective_g == 325
                await _apply_terminal_spool_usage(session, job=job, correlation_id="tare-repeat")
                assert row.remaining_mass_effective_g == 325
                assert job.segments[0].state_snapshot["spool"]["remaining_mass_g"] == "450"
                await session.commit()
            app.dependency_overrides.pop(dependencies.current_user)
            assert (await client.get("/api/v1/locations")).status_code == 401
            assert (await client.get(f"/api/v1/spools/{spool_id}/mass-basis")).status_code == 401
            assert (
                await client.get(
                    "/api/v1/spool-tare-suggestions", params={"filament_product_id": product_ids[0]}
                )
            ).status_code == 401
        await engine.dispose()
