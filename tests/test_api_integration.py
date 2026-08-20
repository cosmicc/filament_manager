"""PostgreSQL-backed API transaction tests."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.api.routes import auth, inventory, operations
from filament_manager.api.routes import imports as import_routes
from filament_manager.config import Settings
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import NotificationSeverity, SpoolStatus, UserRole
from filament_manager.models.inventory import (
    BuildPlate,
    BuildPlateSurface,
    FilamentColor,
    FilamentProduct,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Spool,
    SpoolMeasurement,
    Vendor,
)
from filament_manager.models.operations import (
    AuditEvent,
    ImportRun,
    Notification,
    OutboxJob,
    UserNotificationState,
)
from filament_manager.security import hash_password
from filament_manager.services import events
from filament_manager.services.accounts import ensure_single_administrator
from filament_manager.services.notifications import upsert_notification

WORKBOOK = Path(__file__).parents[1] / "reference" / "Filament Inventory Master.xlsx"


def integration_settings(database_url: str, data_dir: Path | None = None) -> Settings:
    app: dict[str, object] = {
        "base_url": "http://testserver",
        "allowed_hosts": ["testserver"],
        "secure_cookies": False,
    }
    if data_dir is not None:
        app["data_dir"] = data_dir
    return Settings.model_validate(
        {
            "app": app,
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
async def test_unknown_tare_measurement_is_one_audited_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Establish tare, measurement, spool state, audit, and projections atomically."""

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
            administrator = User(
                username="integration-admin",
                normalized_username="integration-admin",
                display_name="Integration Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            vendor = Vendor(name="Test Vendor")
            session.add_all([administrator, vendor])
            await session.flush()
            product = FilamentProduct(
                vendor_id=vendor.id,
                material_type="PETG",
                color_name="Black",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.27"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add(product)
            await session.flush()
            spool = Spool(
                spool_code="TEST-1",
                filament_product_id=product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("0"),
                remaining_mass_expected_g=Decimal("1000"),
                remaining_mass_effective_g=Decimal("1000"),
                weight_confidence="unknown_tare",
                status=SpoolStatus.NEEDS_WEIGHING,
            )
            session.add(spool)
            await session.commit()
            spool_id = spool.id

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "integration-admin"))
                assert user is not None
                return user

        monkeypatch.setattr(inventory, "get_settings", lambda: settings)
        monkeypatch.setattr(events, "get_settings", lambda: settings)
        from filament_manager import config as config_module

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        from filament_manager import main

        monkeypatch.setattr(main, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        app.dependency_overrides[dependencies.current_user] = user_override

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                f"/api/v1/spools/{spool_id}/measurements",
                headers={"Idempotency-Key": "integration-measurement-001"},
                json={"gross_mass_g": "1012.4", "tare_mass_g": "212.4", "source": "manual"},
            )

        assert response.status_code == 201, response.text
        assert response.json()["net_mass_g"] == "800.000"
        async with factory() as session:
            stored_spool = await session.get(Spool, spool_id)
            assert stored_spool is not None
            assert stored_spool.tare_mass_g == Decimal("212.400")
            assert stored_spool.remaining_mass_effective_g == Decimal("800.000")
            assert stored_spool.record_version == 2
            assert await session.scalar(select(func.count(SpoolMeasurement.id))) == 1
            assert await session.scalar(select(func.count(OutboxJob.id))) == 2
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "spool.measurement.accept")
            )
            assert audit is not None
            assert audit.object_id is not None

        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_system_route_creates_configured_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed configured printers and build plates through an Administrator web action."""

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
            administrator = User(
                username="integration-admin",
                normalized_username="integration-admin",
                display_name="Integration Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            session.add(administrator)
            await session.commit()

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "integration-admin"))
                assert user is not None
                return user

        monkeypatch.setattr(operations, "get_settings", lambda: settings)
        monkeypatch.setattr(inventory, "get_settings", lambda: settings)
        from filament_manager import config as config_module

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        from filament_manager import main

        monkeypatch.setattr(main, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        app.dependency_overrides[dependencies.current_user] = user_override

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            seeded = await client.post("/api/v1/system/seed")
            seeded_again = await client.post("/api/v1/system/seed")
            red_one = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PLA",
                    "color_name": "Red",
                    "color_hex": "FF0000",
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.24",
                    "nominal_net_mass_g": "1000",
                },
            )
            red_two = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PETG",
                    "color_name": "red",
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.27",
                    "nominal_net_mass_g": "1000",
                },
            )
            multicolor_one = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PLA",
                    "product_name": "Blend A",
                    "color_name": "Galaxy",
                    "color_mode": "multicolor",
                    "color_hexes": ["FF0000", "0000FF"],
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.24",
                    "nominal_net_mass_g": "1000",
                },
            )
            multicolor_two = await client.post(
                "/api/v1/filaments",
                json={
                    "material_type": "PETG",
                    "product_name": "Blend B",
                    "color_name": "Galaxy",
                    "color_mode": "multicolor",
                    "color_hexes": ["00FF00", "FFFF00", "800080"],
                    "diameter_mm": "1.75",
                    "density_g_cm3": "1.27",
                    "nominal_net_mass_g": "1000",
                },
            )
            recolored = await client.patch(
                f"/api/v1/filaments/{red_one.json()['id']}",
                json={"expected_version": 1, "color_hex": "A00000"},
            )
            setup_spool = await client.post(
                "/api/v1/spools",
                json={
                    "spool_code": "SETUP-ERROR",
                    "filament_product_id": red_one.json()["id"],
                    "nominal_net_mass_g": "1000",
                    "initial_gross_mass_g": "1152",
                },
            )
            deleted_setup_spool = await client.delete(f"/api/v1/spools/{setup_spool.json()['id']}")
            tracked_spool = await client.post(
                "/api/v1/spools",
                json={
                    "spool_code": "TRACKED-RED",
                    "filament_product_id": red_one.json()["id"],
                    "nominal_net_mass_g": "1000",
                    "initial_gross_mass_g": "1152",
                },
            )
            corrected_spool = await client.patch(
                f"/api/v1/spools/{tracked_spool.json()['id']}",
                json={
                    "expected_version": tracked_spool.json()["record_version"],
                    "remaining_mass_g": "925",
                },
            )
            archived_spool = await client.delete(f"/api/v1/spools/{tracked_spool.json()['id']}")
            locked_color = await client.patch(
                f"/api/v1/filaments/{red_one.json()['id']}",
                json={
                    "expected_version": recolored.json()["record_version"],
                    "color_name": "Dark Red",
                    "color_hex": "800000",
                    "color_mode": "solid",
                    "color_hexes": ["800000"],
                },
            )
            remembered_colors = await client.get("/api/v1/filament-colors")
            printers_response = await client.get("/api/v1/printers")
            template = await client.post(
                "/api/v1/profiles/templates",
                json={
                    "name": "Template PLA",
                    "material_type": "PLA",
                    "printer_id": printers_response.json()[0]["id"],
                    "nozzle_diameter_mm": "0.4",
                    "filament_diameter_mm": "1.75",
                    "settings": {
                        "extruder_temp_c": "205",
                        "bed_temp_c": "60",
                        "flow_percent": "100",
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "100",
                        "filament_density_g_cm3": "1.24",
                    },
                },
            )
            assert template.status_code == 201, template.text
            template_revision_id = template.json()["revisions"][0]["id"]
            published_template = await client.post(
                f"/api/v1/profiles/templates/{template.json()['id']}/revisions/{template_revision_id}/publish"
            )
            assert published_template.status_code == 200, published_template.text
            profile = await client.post(
                "/api/v1/profiles",
                json={
                    "filament_product_id": red_one.json()["id"],
                    "printer_id": printers_response.json()[0]["id"],
                    "nozzle_diameter_mm": "0.4",
                    "extruder_temp_c": "210",
                    "bed_temp_c": "60",
                    "flow_percent": "100",
                    "cooling_min_percent": "20",
                    "cooling_max_percent": "100",
                    "filament_density_g_cm3": "1.24",
                    "cura_extensions": {"xy_offset": "0.05"},
                    "base_template_revision_id": template_revision_id,
                },
            )
            profile_revision = await client.post(
                f"/api/v1/profiles/{profile.json()['id']}/revisions",
                json={
                    "expected_profile_version": 1,
                    "settings": {
                        "extruder_temp_c": "215",
                        "bed_temp_c": "60",
                        "flow_percent": "99",
                        "cooling_min_percent": "20",
                        "cooling_max_percent": "100",
                        "filament_density_g_cm3": "1.24",
                        "cura_extensions": {
                            "xy_offset": "0.075",
                            "hole_xy_offset": "0.2",
                        },
                    },
                },
            )

        assert seeded.status_code == 200, seeded.text
        assert seeded.json() == {"plates": 5, "printers": 1, "templates": 1}
        assert seeded_again.status_code == 200, seeded_again.text
        assert seeded_again.json() == {"plates": 0, "printers": 0, "templates": 0}
        assert red_one.status_code == 201, red_one.text
        assert red_two.status_code == 201, red_two.text
        assert multicolor_one.status_code == 201, multicolor_one.text
        assert multicolor_two.status_code == 201, multicolor_two.text
        assert multicolor_one.json()["color_hexes"] == ["FF0000", "0000FF"]
        assert multicolor_two.json()["color_hexes"] == ["00FF00", "FFFF00", "800080"]
        assert recolored.status_code == 200, recolored.text
        assert recolored.json()["color_name"] == "Red"
        assert recolored.json()["color_hex"] == "A00000"
        assert setup_spool.status_code == 201, setup_spool.text
        assert Decimal(setup_spool.json()["tare_mass_g"]) == Decimal("152")
        assert Decimal(setup_spool.json()["remaining_mass_effective_g"]) == Decimal("1000")
        assert deleted_setup_spool.json() == {"disposition": "deleted"}
        assert corrected_spool.status_code == 200, corrected_spool.text
        assert Decimal(corrected_spool.json()["remaining_mass_effective_g"]) == Decimal("925")
        assert archived_spool.json() == {"disposition": "archived"}
        assert locked_color.status_code == 409, locked_color.text
        assert locked_color.json()["code"] == "filament_color_locked"
        assert remembered_colors.json()[0]["color_hex"] == "A00000"
        assert profile.status_code == 201, profile.text
        assert profile_revision.status_code == 201, profile_revision.text
        assert profile_revision.json()["version"] == 2
        assert Decimal(profile_revision.json()["extruder_temp_c"]) == Decimal("215")
        assert profile_revision.json()["cura_extensions"] == {
            "xy_offset": "0.075",
            "hole_xy_offset": "0.2",
        }

        async with factory() as session:
            assert await session.scalar(select(func.count(Printer.id))) == 1
            assert await session.scalar(select(func.count(BuildPlate.id))) == 5
            assert await session.scalar(select(func.count(BuildPlateSurface.id))) == 5
            asa_template = await session.scalar(
                select(MaterialTemplate).where(MaterialTemplate.material_type == "ASA")
            )
            assert asa_template is not None
            assert asa_template.name == "Template ASA"
            assert asa_template.active is True
            asa_revision = await session.scalar(
                select(MaterialTemplateRevision).where(
                    MaterialTemplateRevision.material_template_id == asa_template.id
                )
            )
            assert asa_revision is not None
            assert asa_revision.settings["extruder_temp_c"] == "245"
            assert asa_revision.settings["bed_temp_c"] == "95"
            assert asa_revision.settings["filament_density_g_cm3"] == "1.07"
            assert await session.scalar(select(func.count(FilamentColor.id))) == 1
            products = list(
                await session.scalars(select(FilamentProduct).order_by(FilamentProduct.material_type))
            )
            red_products = [product for product in products if product.color_name.casefold() == "red"]
            galaxy_products = {
                product.product_name: product.color_hexes
                for product in products
                if product.color_name == "Galaxy"
            }
            assert [product.color_hex for product in red_products] == ["A00000", "A00000"]
            assert galaxy_products == {
                "Blend A": ["FF0000", "0000FF"],
                "Blend B": ["00FF00", "FFFF00", "800080"],
            }
            audit = await session.scalar(select(AuditEvent).where(AuditEvent.action == "system.seed.web"))
            assert audit is not None
            assert audit.after == {"plates": 5, "printers": 1, "templates": 1}

        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_single_account_password_identity_and_session_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enforce first-login replacement and singleton account editing."""

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
            assert await ensure_single_administrator(session) is True
            administrator = await session.scalar(select(User))
            assert administrator is not None
            plate = BuildPlate(plate_code="P1", display_name="Test Plate")
            session.add(plate)
            await session.flush()
            plate_surface = BuildPlateSurface(
                build_plate_id=plate.id,
                side="a",
                surface_code="P1",
                klipper_mesh_profile="P1",
            )
            session.add(plate_surface)
            await session.commit()
            administrator_id = administrator.id
            plate_id = plate.id
            plate_surface_id = plate_surface.id

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        monkeypatch.setattr(auth, "get_settings", lambda: settings)
        monkeypatch.setattr(auth, "login_limiter", auth.LoginRateLimiter())
        monkeypatch.setattr(events, "get_settings", lambda: settings)
        from filament_manager import config as config_module

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        from filament_manager import main

        monkeypatch.setattr(main, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as admin:
            login = await admin.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "admin"},
            )
            assert login.status_code == 200, login.text
            assert login.json()["user"]["must_change_password"] is True
            blocked = await admin.get("/api/v1/settings/operational")
            assert blocked.status_code == 403
            assert blocked.json()["code"] == "password_change_required"
            assert (await admin.get("/api/v1/auth/me")).status_code == 200
            csrf = admin.cookies[dependencies.CSRF_COOKIE]
            headers = {"X-CSRF-Token": csrf}
            changed = await admin.post(
                "/api/v1/auth/change-password",
                headers=headers,
                json={
                    "current_password": "admin",
                    "new_password": "permanent administrator password",
                },
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["must_change_password"] is False
            assert (await admin.get("/api/v1/settings/operational")).status_code == 200
            accounts = await admin.get("/api/v1/auth/users")
            assert accounts.status_code == 200
            assert [account["username"] for account in accounts.json()] == ["admin"]
            rejected_role = await admin.patch(
                f"/api/v1/auth/users/{administrator_id}",
                headers=headers,
                json={"expected_version": 2, "role": "operator"},
            )
            assert rejected_role.status_code == 422
            created = await admin.post(
                "/api/v1/auth/users",
                headers=headers,
                json={
                    "username": "managed-viewer",
                    "display_name": "Managed Viewer",
                    "password": "temporary viewer password",
                    "role": "viewer",
                },
            )
            assert created.status_code == 405
            renamed = await admin.patch(
                f"/api/v1/auth/users/{administrator_id}",
                headers=headers,
                json={
                    "expected_version": 2,
                    "username": "owner",
                    "display_name": "Printer Owner",
                },
            )
            assert renamed.status_code == 200, renamed.text
            assert renamed.json()["username"] == "owner"

            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as other:
                other_login = await other.post(
                    "/api/v1/auth/login",
                    json={
                        "username": "owner",
                        "password": "permanent administrator password",
                    },
                )
                assert other_login.status_code == 200, other_login.text
                changed_again = await admin.post(
                    "/api/v1/auth/change-password",
                    headers=headers,
                    json={
                        "current_password": "permanent administrator password",
                        "new_password": "replacement administrator password",
                    },
                )
                assert changed_again.status_code == 200, changed_again.text
                assert (await other.get("/api/v1/settings/operational")).status_code == 401

            cleaned = await admin.post(
                f"/api/v1/build-plates/{plate_id}/maintenance-events",
                headers=headers,
                json={"maintenance_type": "cleaned", "notes": "Routine cleaning"},
            )
            assert cleaned.status_code == 201, cleaned.text
            mesh_calibrated = await admin.post(
                f"/api/v1/build-plates/{plate_id}/maintenance-events",
                headers=headers,
                json={
                    "maintenance_type": "mesh_calibrated",
                    "surface_id": str(plate_surface_id),
                },
            )
            assert mesh_calibrated.status_code == 201, mesh_calibrated.text
            maintenance = await admin.get(f"/api/v1/build-plates/maintenance/events?plate_id={plate_id}")
            assert maintenance.status_code == 200
            assert [item["maintenance_type"] for item in maintenance.json()] == [
                "mesh_calibrated",
                "cleaned",
            ]
            due_status = await admin.get("/api/v1/build-plates/maintenance/status")
            assert due_status.status_code == 200
            assert due_status.json()[0]["cleaning_due"] is False
            assert due_status.json()[0]["surfaces"][0]["mesh_due"] is False
            reset = await admin.post(
                f"/api/v1/auth/users/{administrator_id}/reset-password",
                headers=headers,
                json={"expected_version": 4, "temporary_password": "replacement password"},
            )
            assert reset.status_code in {404, 405}

        async with factory() as session:
            notification = await upsert_notification(
                session,
                deduplication_key="test:moonraker:unavailable",
                category="moonraker_unavailable",
                severity=NotificationSeverity.ERROR,
                title="Printer unavailable",
                message="The test printer cannot be reached.",
                action_path="/integrations",
                object_type=None,
                object_id=None,
            )
            await session.flush()
            notification_id = notification.id
            session.add(
                UserNotificationState(
                    user_id=administrator_id,
                    notification_id=notification_id,
                    read_at=datetime.now(UTC),
                )
            )
            notification.active = False
            notification.resolved_at = datetime.now(UTC)
            await session.commit()
            reactivated = await upsert_notification(
                session,
                deduplication_key="test:moonraker:unavailable",
                category="moonraker_unavailable",
                severity=NotificationSeverity.ERROR,
                title="Printer unavailable",
                message="The test printer cannot be reached.",
                action_path="/integrations",
                object_type=None,
                object_id=None,
            )
            await session.commit()
            assert reactivated.active is True
            assert reactivated.occurrence_count == 2
            assert (
                await session.get(
                    UserNotificationState,
                    {"user_id": administrator_id, "notification_id": notification_id},
                )
                is None
            )
            assert await session.get(Notification, notification_id) is not None

        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workbook_upload_dry_run_and_commit_populates_inventory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Validate and commit an uploaded master workbook without CLI path handling."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = integration_settings(database_url, tmp_path)
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            administrator = User(
                username="integration-admin",
                normalized_username="integration-admin",
                display_name="Integration Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            session.add(administrator)
            await session.commit()

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "integration-admin"))
                assert user is not None
                return user

        monkeypatch.setattr(import_routes, "get_settings", lambda: settings)
        monkeypatch.setattr(events, "get_settings", lambda: settings)
        from filament_manager import config as config_module

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        from filament_manager import main

        monkeypatch.setattr(main, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        app.dependency_overrides[dependencies.current_user] = user_override

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with WORKBOOK.open("rb") as workbook:
                dry_run = await client.post(
                    "/api/v1/imports/workbook/dry-run",
                    files={
                        "file": (
                            "Filament Inventory Master.xlsx",
                            workbook,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    },
                )

            assert dry_run.status_code == 201, dry_run.text
            dry_run_payload = dry_run.json()
            run_id = UUID(dry_run_payload["id"])
            assert dry_run_payload["status"] == "validated"
            assert dry_run_payload["stored_workbook"] is True
            assert dry_run_payload["report"]["valid_rows"] == 35
            assert (tmp_path / "workbook-imports" / f"{run_id}.xlsx").is_file()

            committed = await client.post(f"/api/v1/imports/workbook/{run_id}/commit")

        assert committed.status_code == 200, committed.text
        assert committed.json()["spools"] == 35

        async with factory() as session:
            stored_run = await session.get(ImportRun, run_id)
            assert stored_run is not None
            assert stored_run.status == "committed"
            assert await session.scalar(select(func.count(Spool.id))) == 35
            assert await session.scalar(select(func.count(Printer.id))) == 1
            assert await session.scalar(select(func.count(BuildPlate.id))) == 5
            assert await session.scalar(select(func.count(OutboxJob.id))) == 66
            assert (
                await session.scalar(
                    select(func.count(OutboxJob.id)).where(OutboxJob.job_type == "spoolman.spool.upsert")
                )
                == 35
            )
            assert (
                await session.scalar(
                    select(func.count(OutboxJob.id)).where(OutboxJob.job_type == "google.profile.publish")
                )
                == committed.json()["profiles"]
            )
            assert (
                await session.scalar(
                    select(func.count(OutboxJob.id)).where(OutboxJob.job_type == "google.inventory.publish")
                )
                == 1
            )
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "workbook.import.commit")
            )
            assert audit is not None
            assert audit.source == "web"
            seed_audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "system.seed.auto")
            )
            assert seed_audit is not None
            assert seed_audit.after == {"plates": 5, "printers": 1, "templates": 1}

        await engine.dispose()
