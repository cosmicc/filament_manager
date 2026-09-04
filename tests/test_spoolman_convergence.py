"""PostgreSQL-backed tests for complete canonical-to-Spoolman convergence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.models import Base
from filament_manager.models.enums import JobStatus
from filament_manager.models.inventory import FilamentProduct, Spool, Vendor
from filament_manager.models.operations import OutboxJob, ProjectionState
from filament_manager.workers import dispatcher
from filament_manager.workers.dispatcher import _converge_spoolman, claim_jobs


class RecordingSpoolmanClient:
    """Record duplicate-safe create/update behavior without external I/O."""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.updated: list[str] = []
        self.filament_payloads: list[dict[str, object]] = []
        self.spool_updates: list[dict[str, object]] = []

    async def list_vendors(self) -> list[dict[str, object]]:
        return []

    async def list_filaments(self) -> list[dict[str, object]]:
        return []

    async def list_spools(self) -> list[dict[str, object]]:
        return []

    async def find_managed_vendor(self, vendor_uuid: str) -> None:
        return None

    async def find_vendors(self, name: str) -> list[dict[str, object]]:
        return []

    async def create_vendor(self, payload: dict[str, object]) -> dict[str, object]:
        self.created.append("vendor")
        return {"id": 11, **payload}

    async def update_vendor(self, vendor_id: int, payload: dict[str, object]) -> dict[str, object]:
        self.updated.append("vendor")
        return {"id": vendor_id, **payload}

    async def find_managed_filament(self, product_uuid: str) -> None:
        return None

    async def create_filament(self, payload: dict[str, object]) -> dict[str, object]:
        self.created.append("filament")
        self.filament_payloads.append(payload)
        return {"id": 22, **payload}

    async def update_filament(self, filament_id: int, payload: dict[str, object]) -> dict[str, object]:
        self.updated.append("filament")
        self.filament_payloads.append(payload)
        return {"id": filament_id, **payload}

    async def find_managed_spool(self, spool_uuid: str) -> None:
        return None

    async def create_spool(self, payload: dict[str, object]) -> dict[str, object]:
        self.created.append("spool")
        return {"id": 33, **payload}

    async def update_spool(self, spool_id: int, payload: dict[str, object]) -> dict[str, object]:
        self.updated.append("spool")
        self.spool_updates.append(payload)
        return {"id": spool_id, **payload}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_convergence_seeds_existing_inventory_and_then_updates_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sweep projects pre-existing rows and remains duplicate-safe on later runs."""

    monkeypatch.setattr(
        dispatcher,
        "get_settings",
        lambda: SimpleNamespace(moonraker=SimpleNamespace(printers=[SimpleNamespace(id="test")])),
    )

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            vendor = Vendor(name="Convergence Materials")
            product = FilamentProduct(
                vendor=vendor,
                material_type="PLA",
                color_name="Red",
                filler="Carbon Fiber",
                finish="Matte",
                color_hex="FF0000",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
            )
            spool = Spool(
                spool_code="SYNC-001",
                filament_product=product,
                nominal_net_mass_g=Decimal("1000"),
                tare_mass_g=Decimal("200"),
                remaining_mass_expected_g=Decimal("1000"),
                remaining_mass_effective_g=Decimal("1000"),
                weight_confidence="estimated",
                location="Bucket 1",
                location_authoritative=True,
            )
            session.add(spool)
            await session.commit()
            spool_id: UUID = spool.id
            product_id: UUID = product.id

        client = RecordingSpoolmanClient()
        async with factory() as session:
            await _converge_spoolman(session, client)  # type: ignore[arg-type]
            await session.commit()

        assert client.created == ["vendor", "filament", "spool"]
        assert client.filament_payloads[-1]["name"] == "PLA · Red · Carbon Fiber · Matte"
        async with factory() as session:
            projected = await session.get(Spool, spool_id)
            assert projected is not None
            assert projected.spoolman_id == 33
            assert projected.record_version == 2
            product_projection = await session.scalar(
                select(ProjectionState).where(
                    ProjectionState.system == "spoolman",
                    ProjectionState.object_type == "filament_product",
                    ProjectionState.object_id == product_id,
                )
            )
            assert product_projection is not None
            assert product_projection.acknowledged_version == product.record_version
            assert product_projection.last_success_at is not None

        async with factory() as session:
            await _converge_spoolman(session, client)  # type: ignore[arg-type]
            await session.commit()

        assert client.created == ["vendor", "filament", "spool"]
        assert client.updated == ["vendor", "filament", "spool"]
        assert "remaining_weight" not in client.spool_updates[-1]
        async with factory() as session:
            projected = await session.get(Spool, spool_id)
            assert projected is not None
            assert projected.record_version == 2

            stale_job = OutboxJob(
                job_type="spoolman.spool.upsert",
                idempotency_key="stale-running-recovery",
                aggregate_type="spool",
                aggregate_id=spool_id,
                aggregate_version=projected.record_version,
                payload={"spool_id": str(spool_id)},
                status=JobStatus.RUNNING,
                attempts=1,
                max_attempts=12,
                next_attempt_at=datetime.now(UTC),
                locked_by="terminated-worker",
                locked_at=datetime.now(UTC) - timedelta(minutes=10),
                created_at=datetime.now(UTC) - timedelta(minutes=10),
            )
            session.add(stale_job)
            await session.commit()
            stale_job_id = stale_job.id

        monkeypatch.setattr(
            dispatcher,
            "get_settings",
            lambda: SimpleNamespace(sync=SimpleNamespace(outbox_lock_timeout_seconds=300)),
        )
        async with factory() as session:
            claimed = await claim_jobs(session, "replacement-worker", limit=1)
        assert [job.id for job in claimed] == [stale_job_id]
        assert claimed[0].locked_by == "replacement-worker"

        await engine.dispose()
