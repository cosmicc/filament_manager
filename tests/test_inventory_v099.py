"""PostgreSQL coverage for uppercase brands and ordered named multicolor identity."""

from collections.abc import AsyncIterator
from decimal import Decimal

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
from filament_manager.models.inventory import FilamentProduct, Spool, Vendor
from filament_manager.models.operations import AuditEvent, OutboxJob
from filament_manager.services import events
from filament_manager.services.manufacturers import manufacturer_name


def test_manufacturer_normalization_bounds_and_unicode() -> None:
    """Normalize all writers consistently and reject unsafe or expanding names."""
    assert manufacturer_name(" eSun ") == "ESUN"
    assert manufacturer_name("Straße") == "STRASSE"
    assert manufacturer_name("Unspecified manufacturer") == "UNKNOWN"
    for invalid in ("\x00", "ß" * 160, " ", "Brand\nName"):
        with pytest.raises(ValueError):
            manufacturer_name(invalid)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rename_and_named_components_are_transactional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Correct live identities, reject stale writes, and preserve physical spool records."""
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
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
            brand = Vendor(name="MAKER")
            session.add_all([user, brand])
            await session.flush()
            product = FilamentProduct(
                vendor_id=brand.id,
                material_type="PLA",
                color_name="Red",
                color_mode="solid",
                color_hex="FF0000",
                color_hexes=["FF0000"],
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
                archived=True,
            )
            session.add(product)
            await session.flush()
            spool = Spool(
                spool_code="P1",
                filament_product_id=product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("500"),
                remaining_mass_effective_g=Decimal("500"),
            )
            session.add(spool)
            await session.commit()

        async def sessions() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def current_user() -> User:
            return user

        from filament_manager import config, main

        for module in (config, main, inventory, events):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = sessions
        app.dependency_overrides[dependencies.current_user] = current_user
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/api/v1/vendors", json={"name": "eSun"})
            assert response.status_code == 201, response.text
            assert response.json()["name"] == "ESUN"
            assert (await client.post("/api/v1/vendors", json={"name": "Esun"})).status_code == 409
            path = f"/api/v1/vendors/{brand.id}"
            payload = {"name": "new maker", "expected_version": 1, "confirm_name": "MAKER"}
            response = await client.patch(path, json=payload)
            assert response.status_code == 200, response.text
            assert response.json()["name"] == "NEW MAKER"
            assert (await client.patch(path, json=payload)).status_code == 409
            conflict = await client.patch(
                path, json={**payload, "expected_version": 2, "confirm_name": "NEW MAKER", "name": "esun"}
            )
            assert conflict.status_code == 409
            product_path = f"/api/v1/filaments/{product.id}"
            response = await client.patch(
                product_path,
                json={
                    "expected_version": 1,
                    "color_name": "Red",
                    "color_mode": "solid",
                    "color_hexes": ["FF0000", "FFFFFF", "0000FF"],
                    "color_names": ["Red", "White", "Blue"],
                },
            )
            assert response.status_code == 200, response.text
            saved = response.json()
            assert saved["color_mode"] == "multicolor"
            assert saved["color_name"] == "Multicolor"
            assert saved["product_name"] == "PLA · Red/White/Blue"
            assert saved["vendor_name"] == "NEW MAKER"
            assert saved["archived"]
            choices = (await client.get("/api/v1/filament-colors")).json()
            assert {item["name"] for item in choices} >= {"Red", "White", "Blue"}
            spool_response = (await client.get(f"/api/v1/spools/{spool.id}")).json()
            assert spool_response["color_names"] == ["Red", "White", "Blue"]
            assert spool_response["product_name"] == "PLA · Red/White/Blue"
            from filament_manager.services.google_workbook import snapshot

            async with factory() as session:
                tabs = await snapshot(session)
                filament_tab = next(tab for tab in tabs if tab.title == "Filaments")
                exported = [dict(zip(filament_tab.fields, row, strict=True)) for row in filament_tab.rows]
                assert exported[0]["name"] == "PLA · Red/White/Blue"
            assert (await client.get("/api/v1/filaments?include_archived=true&search=White")).json()[0][
                "id"
            ] == str(product.id)

            bad = await client.patch(
                product_path,
                json={"expected_version": saved["record_version"], "color_names": ["Blue", "White", "Red"]},
            )
            assert bad.status_code == 422
            response = await client.patch(
                product_path,
                json={
                    "expected_version": saved["record_version"],
                    "color_name": "Red",
                    "color_mode": "solid",
                    "color_hexes": ["FF0000"],
                    "color_names": [],
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["product_name"] == "PLA · Red"
            user.role = UserRole.VIEWER
            assert (await client.patch(path, json=payload)).status_code == 403
        async with factory() as session:
            retained = await session.get(Spool, spool.id)
            assert retained.spool_code == "P1" and retained.filament_product_id == product.id
            assert retained.remaining_mass_effective_g == Decimal("500")
            assert await session.scalar(select(AuditEvent).where(AuditEvent.action == "vendor.rename"))
            assert await session.scalar(
                select(OutboxJob).where(OutboxJob.job_type == "spoolman.reconcile.full")
            )
        await engine.dispose()


@pytest.mark.integration
def test_populated_upgrade_merges_brands_without_merging_products(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retain physical links and captured history while normalizing duplicate brands."""
    from uuid import uuid4

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from test_migrations import insert_legacy_record

    from filament_manager.config import get_settings
    from filament_manager.models.enums import PrintJobStatus
    from filament_manager.models.inventory import FilamentColor, Printer
    from filament_manager.models.printing import PrintJob

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", url)
        get_settings.cache_clear()
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "a0678b901234")
        engine = create_engine(url)
        with Session(engine) as session:
            first, second = (
                Vendor(name="eSun", notes="First", aliases=["Old"]),
                Vendor(name="ESUN", notes="Second", preferred=True),
            )
            session.add_all([first, second])
            session.flush()
            products = []
            for vendor in (first, second):
                product = FilamentProduct(
                    vendor_id=vendor.id,
                    material_type="PLA",
                    color_name="Multicolor",
                    color_mode="multicolor",
                    color_hex="FF0000",
                    color_hexes=["FF0000", "FFFFFF", "0000FF"],
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                )
                insert_legacy_record(session, product)
                products.append(product)
            printer = Printer(
                id=uuid4(),
                printer_code="test",
                name="Test",
                moonraker_base_url="http://test.invalid",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add(printer)
            for name, sample in (("Red", "FF0000"), ("White", "FFFFFF")):
                session.add(
                    FilamentColor(
                        name=name,
                        normalized_name=name.lower(),
                        color_mode="solid",
                        color_hex=sample,
                        color_hexes=[sample],
                    )
                )
            spool = Spool(
                spool_code="P1",
                filament_product_id=products[0].id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("500"),
                remaining_mass_effective_g=Decimal("500"),
            )
            session.add(spool)
            session.flush()
            history = PrintJob(
                printer_id=printer.id,
                spool_id=spool.id,
                filament_product_id=products[0].id,
                filename="test.gcode",
                status=PrintJobStatus.COMPLETED,
                state_snapshot={"vendor_name": "eSun", "color_name": "Multicolor"},
            )
            session.add(history)
            session.commit()
            product_ids = [item.id for item in products]
            spool_id, job_id, survivor_id = spool.id, history.id, second.id
        command.upgrade(cfg, "head")
        command.check(cfg)
        with Session(engine) as session:
            vendor = session.get(Vendor, survivor_id)
            assert vendor.name == "ESUN" and vendor.preferred
            assert {"eSun", "Old", "ESUN"}.issubset(set(vendor.aliases))
            assert set(vendor.notes.split("\n\n")) == {"First", "Second"}
            assert list(session.scalars(select(Vendor.id).where(Vendor.name == "ESUN"))) == [survivor_id]
            for identifier in product_ids:
                product = session.get(FilamentProduct, identifier)
                assert product.vendor_id == survivor_id
                assert product.color_names == ["Red", "White", "#0000FF"]
                assert product.display_name == "PLA · Red/White/#0000FF"
            assert session.get(Spool, spool_id).filament_product_id == product_ids[0]
            assert session.get(PrintJob, job_id).state_snapshot == {
                "vendor_name": "eSun",
                "color_name": "Multicolor",
            }
            assert (
                session.scalar(
                    text("SELECT count(*) FROM audit_events WHERE action = 'vendor.uppercase_merge'")
                )
                == 1
            )
        with pytest.raises(RuntimeError, match="Cannot discard multicolor names"):
            command.downgrade(cfg, "a0678b901234")
        engine.dispose()
        get_settings.cache_clear()
