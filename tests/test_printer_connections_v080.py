"""Database-backed encrypted printer ownership and dashboard isolation contracts."""

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager import config, main
from filament_manager.api import dependencies
from filament_manager.api.routes import inventory, operations, printer_connections
from filament_manager.clients.moonraker import MoonrakerClient, MoonrakerError
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.models.inventory import FilamentProduct, Printer, Spool
from filament_manager.services import events
from filament_manager.services.credentials import CredentialError, writable_cipher
from filament_manager.services.printer_connections import configured_printers


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///etc/passwd",
        "http://169.254.169.254",
        "http://localhost",
        "http://[::1]",
        "http://metadata.google.internal",
        "https://user:secret@printer.test",
        "http://printer.test/path",
        "https://printer.test?token=secret",
        "http://printer.test:0",
    ],
)
def test_printer_endpoint_validation(endpoint: str) -> None:
    with pytest.raises(ValueError):
        printer_connections.ConnectionFields(base_url=endpoint)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connections_remain_private_and_dashboard_scopes_each_printer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        settings = integration_settings(postgres.get_connection_url(), tmp_path)
        engine = create_async_engine(postgres.get_connection_url())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            user = User(
                username="admin",
                normalized_username="admin",
                display_name="Admin",
                password_hash="unused",
                role=UserRole.ADMINISTRATOR,
            )
            legacy = Printer(
                printer_code="test-printer",
                name="First printer",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=0.4,
            )
            session.add_all([user, legacy])
            await session.commit()
            legacy_id = legacy.id

        async def sessions() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def current_user() -> User:
            return user

        for module in (config, main, operations, inventory, printer_connections, events):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        monkeypatch.setattr(
            MoonrakerClient, "operational_state", AsyncMock(side_effect=MoonrakerError("unavailable"))
        )
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = sessions
        app.dependency_overrides[dependencies.current_user] = current_user
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as client:
            created = await client.post(
                "/api/v1/printers",
                json={
                    "name": "Second printer",
                    "base_url": "http://second-printer.test:7125",
                    "api_key": "test-private-key",
                    "extruder_count": 2,
                    "heated_chamber": True,
                    "max_extruder_temp_c": "300",
                    "max_bed_temp_c": "120",
                },
            )
            assert created.status_code == 201, created.text
            second_id = created.json()["id"]
            assert created.json()["extruder_count"] == 2
            assert "test-private-key" not in created.text and "second-printer.test" not in created.text
            async with factory() as session:
                connections = await configured_printers(session, settings)
                assert len(connections) == 2
                assert connections[1].resolved_api_key() == "test-private-key"
                stored = await session.scalar(select(Printer).where(Printer.id == second_id))
                assert stored and stored.encrypted_api_key != "test-private-key"
            private = await client.get(f"/api/v1/printers/{second_id}/connection")
            assert private.json()["has_api_key"] is True
            assert "test-private-key" not in private.text
            listing = await client.get("/api/v1/printers")
            assert "encrypted_api_key" not in listing.text and "base_url" not in listing.text
            summary = await client.get("/api/v1/dashboard")
            assert summary.status_code == 200, summary.text
            contexts = summary.json()["printer_contexts"]
            assert {item["printer_id"] for item in contexts} == {str(legacy_id), second_id}
            assert all(item["printer_state"]["connection_status"] == "unavailable" for item in contexts)
            assert all(item["active_spools"] == [] and item["active_plate"] is None for item in contexts)
            assert "second-printer.test" not in summary.text
            duplicate = await client.post(
                "/api/v1/printers", json={"name": "Duplicate", "base_url": "http://second-printer.test:7125/"}
            )
            assert duplicate.status_code == 409
            corrected = await client.put(
                f"/api/v1/printers/{second_id}/connection",
                json={
                    "base_url": "http://corrected-printer.test:7125",
                    "expected_version": 1,
                    "enabled": True,
                },
            )
            assert corrected.status_code == 200, corrected.text
            async with factory() as session:
                connections = await configured_printers(session, settings)
                assert str(connections[1].base_url).rstrip("/") == "http://corrected-printer.test:7125"
                assert connections[1].resolved_api_key() == "test-private-key"
            user.role = UserRole.VIEWER
            assert (await client.get(f"/api/v1/printers/{second_id}/connection")).status_code == 403
            user.role = UserRole.ADMINISTRATOR
            async with factory() as session:
                product = FilamentProduct(
                    material_type="PLA",
                    color_name="Blue",
                    diameter_mm=1.75,
                    density_g_cm3=1.24,
                    nominal_net_mass_g=1000,
                )
                session.add(product)
                await session.flush()
                for index, printer_id in enumerate((legacy_id, UUID(second_id))):
                    session.add(
                        Spool(
                            spool_code=f"CONTEXT-{index}",
                            filament_product_id=product.id,
                            nominal_net_mass_g=1000,
                            tare_mass_g=200,
                            remaining_mass_expected_g=800,
                            remaining_mass_effective_g=800,
                            active_printer_id=printer_id,
                            active_extruder="extruder",
                        )
                    )
                await session.commit()
            summary = await client.get("/api/v1/dashboard")
            assert summary.status_code == 200, summary.text
            context_spools = {
                item["printer_id"]: [spool["spool_code"] for spool in item["active_spools"]]
                for item in summary.json()["printer_contexts"]
            }
            assert context_spools == {str(legacy_id): ["CONTEXT-0"], second_id: ["CONTEXT-1"]}
            unverified = await client.post(
                f"/api/v1/printer-context/active-spool/clear?printer_id={second_id}&extruder=extruder1"
            )
            assert unverified.status_code == 409
            assert unverified.json()["code"] == "tool_routines_unverified"
            preview = await client.get(f"/api/v1/spools/next-code?filament_product_id={product.id}")
            assert preview.json() == {"spool_code": "P1"}
            new_spool = await client.post(
                "/api/v1/spools",
                json={
                    "filament_product_id": str(product.id),
                    "nominal_net_mass_g": "1000",
                    "tare_mass_g": "200",
                    "spool_code": "legacy-client-choice",
                },
            )
            assert new_spool.status_code == 201, new_spool.text
            assert new_spool.json()["spool_code"] == "P1"
            immutable = await client.patch(
                f"/api/v1/spools/{new_spool.json()['id']}",
                json={
                    "expected_version": new_spool.json()["record_version"],
                    "spool_code": "P99",
                },
            )
            assert immutable.status_code == 409
            assert immutable.json()["code"] == "spool_identity_locked"
            preview = await client.get(f"/api/v1/spools/next-code?filament_product_id={product.id}")
            assert preview.json() == {"spool_code": "P2"}
            # Losing the shared key while another integration uses it must not
            # silently create a new key during a new setup request.
            key = tmp_path / "credentials/integration.key"
            key.rename(tmp_path / "retained.key")
            async with factory() as session:
                with pytest.raises(CredentialError):
                    await writable_cipher(session, settings)
            assert not key.exists()
        await engine.dispose()
