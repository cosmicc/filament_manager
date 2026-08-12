"""PostgreSQL-backed Spoolman bucket-location ownership tests."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api.routes.inventory import update_spool
from filament_manager.api.schemas import SpoolUpdate
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import SpoolStatus, UserRole
from filament_manager.models.inventory import FilamentProduct, Spool
from filament_manager.models.operations import AuditEvent, OutboxJob
from filament_manager.services import events
from filament_manager.workers.dispatcher import _reconcile_spoolman


class FakeSpoolmanClient:
    """Small supported-contract fake that exposes one projected spool."""

    def __init__(self, spool_id: UUID) -> None:
        self.spool_id = spool_id
        self.location: str | None = "Bucket 17"
        self.location_updates: list[str | None] = []

    def _remote(self) -> dict[str, object]:
        return {
            "id": 7,
            "remaining_weight": "1000",
            "location": self.location,
            "extra": {"filament_manager_spool_uuid": str(self.spool_id)},
        }

    async def list_spools(self) -> list[dict[str, object]]:
        return [self._remote()]

    async def update_spool(self, spool_id: int, managed_payload: dict[str, object]) -> dict[str, object]:
        assert spool_id == 7
        location = managed_payload.get("location")
        assert location is None or isinstance(location, str)
        self.location = location
        self.location_updates.append(location)
        return self._remote()


def test_spool_location_input_is_trimmed_and_can_be_cleared() -> None:
    """Free-text bucket input is normalized without creating a controlled list."""

    assert SpoolUpdate(expected_version=1, location="  Bucket 17  ").location == "Bucket 17"
    assert SpoolUpdate(expected_version=1, location="   ").location is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciliation_adopts_location_once_then_repairs_remote_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty legacy row imports once; subsequent Spoolman edits are overwritten."""

    runtime_settings = SimpleNamespace(sync=SimpleNamespace(max_retry_attempts=12))
    monkeypatch.setattr(events, "get_settings", lambda: runtime_settings)

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            administrator = User(
                username="location-admin",
                normalized_username="location-admin",
                display_name="Location Administrator",
                password_hash="not-used-in-this-test",
                role=UserRole.ADMINISTRATOR,
            )
            product = FilamentProduct(
                material_type="PLA",
                color_name="Blue",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add_all([administrator, product])
            await session.flush()
            spool = Spool(
                spool_code="BUCKET-TEST",
                filament_product_id=product.id,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("1000"),
                remaining_mass_effective_g=Decimal("1000"),
                weight_confidence="estimated",
                status=SpoolStatus.IN_STOCK,
                location=None,
                location_authoritative=False,
                spoolman_id=7,
            )
            session.add(spool)
            await session.commit()
            spool_id = spool.id
            administrator_id = administrator.id

        fake_client = FakeSpoolmanClient(spool_id)
        async with factory() as session:
            await _reconcile_spoolman(session, fake_client)  # type: ignore[arg-type]
            await session.commit()

        async with factory() as session:
            imported = await session.get(Spool, spool_id)
            assert imported is not None
            assert imported.location == "Bucket 17"
            assert imported.location_authoritative is True
            assert imported.record_version == 2
            audit = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "spool.location.import")
            )
            assert audit is not None
            google_job = await session.scalar(
                select(OutboxJob).where(OutboxJob.job_type == "google.inventory.publish")
            )
            assert google_job is not None

        async with factory() as session:
            administrator = await session.get(User, administrator_id)
            assert administrator is not None
            await update_spool(
                spool_id,
                SpoolUpdate(expected_version=2, location=None),
                SimpleNamespace(state=SimpleNamespace(correlation_id="location-clear-test")),  # type: ignore[arg-type]
                administrator,
                session,
            )

        fake_client.location = "Bucket 99"
        async with factory() as session:
            await _reconcile_spoolman(session, fake_client)  # type: ignore[arg-type]
            await session.commit()

        async with factory() as session:
            canonical = await session.get(Spool, spool_id)
            assert canonical is not None
            assert canonical.location is None
            assert canonical.location_authoritative is True
            assert canonical.record_version == 3
            projection_job = await session.scalar(
                select(OutboxJob).where(
                    OutboxJob.job_type == "spoolman.spool.upsert",
                    OutboxJob.aggregate_version == 3,
                )
            )
            assert projection_job is not None
        assert fake_client.location_updates == [None]

        await engine.dispose()
