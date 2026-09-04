"""Validate canonical projections against the pinned real Spoolman REST service."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer

from filament_manager.api.schemas import MaterialSettingsInput
from filament_manager.clients.spoolman import SpoolmanClient
from filament_manager.config import SpoolmanConfig
from filament_manager.models import Base
from filament_manager.models.enums import ProfileStatus, SpoolStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Nozzle,
    Printer,
    Spool,
)
from filament_manager.models.operations import OutboxJob
from filament_manager.services import events
from filament_manager.services.material_settings import create_published_profile_snapshot
from filament_manager.workers import dispatcher
from filament_manager.workers.dispatcher import _converge_spoolman


async def _add_profile(
    session: AsyncSession,
    product: FilamentProduct,
    printer: Printer,
    *,
    code: str,
    diameter: str,
    extruder: str,
    bed: str,
) -> tuple[Nozzle, MaterialProfile]:
    """Create a valid physical-nozzle/template/profile scope through the save service."""

    nozzle = Nozzle(printer_id=printer.id, nozzle_code=code, diameter_mm=Decimal(diameter), material="Brass")
    session.add(nozzle)
    await session.flush()
    template = MaterialTemplate(
        name=f"Template PLA {code}",
        material_type="PLA",
        printer_id=printer.id,
        nozzle_id=nozzle.id,
        nozzle_diameter_mm=nozzle.diameter_mm,
        filament_diameter_mm=Decimal("1.75"),
    )
    session.add(template)
    await session.flush()
    settings = MaterialSettingsInput(
        extruder_temp_c=Decimal(extruder),
        bed_temp_c=Decimal(bed),
        initial_bed_temp_c=Decimal("80"),
        flow_percent=Decimal("100"),
        cooling_min_percent=Decimal("0"),
        cooling_max_percent=Decimal("100"),
        filament_density_g_cm3=Decimal("1.24"),
    ).model_dump(mode="json")
    revision = MaterialTemplateRevision(
        material_template_id=template.id,
        version=1,
        status=ProfileStatus.PUBLISHED,
        settings=settings,
    )
    session.add(revision)
    await session.flush()
    profile = await create_published_profile_snapshot(
        session,
        filament_product_id=product.id,
        printer_id=printer.id,
        nozzle_diameter_mm=nozzle.diameter_mm,
        base_revision=revision,
        settings=settings,
    )
    return nozzle, profile


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_spoolman_names_and_metadata_preserve_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Metadata updates repair drift without overwriting printer-recorded use."""

    monkeypatch.setattr(
        dispatcher,
        "get_settings",
        lambda: SimpleNamespace(moonraker=SimpleNamespace(printers=[SimpleNamespace(id="test")])),
    )
    monkeypatch.setattr(
        events,
        "get_settings",
        lambda: SimpleNamespace(sync=SimpleNamespace(max_retry_attempts=12)),
    )

    with (
        PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres,
        DockerContainer("ghcr.io/donkie/spoolman:0.23.1")
        .with_env("SPOOLMAN_DB_TYPE", "sqlite")
        .with_exposed_ports(8000) as spoolman,
    ):
        origin = f"http://127.0.0.1:{spoolman.get_exposed_port(8000)}"
        async with httpx.AsyncClient(timeout=2) as http:
            for _ in range(60):
                try:
                    response = await http.get(f"{origin}/api/v1/health")
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.5)
            else:
                pytest.fail("Disposable Spoolman did not become ready")

        engine = create_async_engine(postgres.get_connection_url())
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            client = SpoolmanClient(SpoolmanConfig(base_url=origin))
            await client.ensure_managed_fields()
            async with factory() as session:
                product = FilamentProduct(
                    material_type="PLA",
                    color_name="Blue",
                    filler="Standard",
                    finish="Matte",
                    product_name="Ignored legacy label",
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                    notes="Filament notes",
                )
                spool = Spool(
                    spool_code="SYNC-068",
                    filament_product=product,
                    nominal_net_mass_g=Decimal("1000"),
                    tare_mass_g=Decimal("210"),
                    remaining_mass_expected_g=Decimal("1000"),
                    remaining_mass_effective_g=Decimal("1000"),
                    purchase_cost=Decimal("24.50"),
                    notes="Spool notes",
                )
                session.add(spool)
                await session.flush()
                printer = Printer(
                    printer_code="test",
                    name="Test printer",
                    moonraker_base_url="http://printer.invalid",
                    nozzle_diameter_mm=Decimal("0.4"),
                )
                session.add(printer)
                await session.flush()
                nozzle, profile = await _add_profile(
                    session,
                    product,
                    printer,
                    code="N04",
                    diameter="0.4",
                    extruder="215.5",
                    bed="60.4",
                )
                printer.active_nozzle_id = nozzle.id
                # A newer revision in a different diameter scope must not win.
                other_nozzle, _ = await _add_profile(
                    session,
                    product,
                    printer,
                    code="N06",
                    diameter="0.6",
                    extruder="245",
                    bed="0",
                )
                await _converge_spoolman(session, client)
                await session.commit()
                remote_filaments = await client.list_filaments()
                remote_spools = await client.list_spools()
                assert len(remote_filaments) == len(remote_spools) == 1
                assert remote_filaments[0]["name"] == "PLA · Blue · Matte"
                assert remote_filaments[0]["comment"] == "PLA · Blue · Matte\nFilament notes"
                assert remote_filaments[0]["price"] == 24.5
                assert remote_filaments[0]["spool_weight"] == 210
                assert remote_filaments[0]["settings_extruder_temp"] == 216
                assert remote_filaments[0]["settings_bed_temp"] == 60
                jobs = list(
                    await session.scalars(
                        select(OutboxJob).where(
                            OutboxJob.job_type == "spoolman.filament.upsert",
                        )
                    )
                )
                assert any(job.idempotency_key.startswith(f"profile:{profile.id}:") for job in jobs)
                assert remote_spools[0]["comment"] == "SYNC-068 · PLA · Blue · Matte\nSpool notes"
                assert remote_spools[0]["price"] == 24.5
                assert remote_spools[0]["spool_weight"] == 210
                remote_id = remote_spools[0]["id"]
                await client.set_spool_remaining_weight(remote_id, 725)
                product.finish = "Silk"
                await session.flush()
                await _converge_spoolman(session, client)
                await session.commit()
                refreshed = await client.get_spool(remote_id)
                assert refreshed["remaining_weight"] == 725
                newer_spool = Spool(
                    spool_code="SYNC-068-NEW",
                    filament_product=product,
                    nominal_net_mass_g=Decimal("500"),
                    tare_mass_g=Decimal("180"),
                    remaining_mass_expected_g=Decimal("500"),
                    remaining_mass_effective_g=Decimal("500"),
                    purchase_cost=Decimal("15"),
                    created_at=datetime.now(UTC) + timedelta(seconds=1),
                )
                session.add(newer_spool)
                product.nominal_net_mass_g = Decimal("750")
                printer.active_nozzle_id = other_nozzle.id
                printer.nozzle_diameter_mm = other_nozzle.diameter_mm
                await session.flush()
                await _converge_spoolman(session, client)
                await session.commit()
                refreshed = await client.get_spool(remote_id)
                # (24.50 + 15.00) / (1000 + 500) * 750, without an intermediate rounding.
                assert refreshed["filament"]["price"] == 19.75
                assert refreshed["filament"]["spool_weight"] == 180
                assert refreshed["filament"]["settings_extruder_temp"] == 245
                assert refreshed["filament"]["settings_bed_temp"] == 0
                assert refreshed["price"] == 24.5
                assert refreshed["spool_weight"] == 210
                assert refreshed["remaining_weight"] == 725

                newer_spool.currency = "EUR"
                printer.active_nozzle_id = None
                await session.flush()
                await _converge_spoolman(session, client)
                await session.commit()
                refreshed = await client.get_spool(remote_id)
                assert refreshed["filament"].get("price") is None
                assert refreshed["filament"].get("settings_extruder_temp") is None
                assert refreshed["filament"].get("settings_bed_temp") is None
                assert refreshed["price"] == 24.5
                assert refreshed["remaining_weight"] == 725

                newer_spool.archived = True
                await session.flush()
                await _converge_spoolman(session, client)
                await session.commit()
                refreshed = await client.get_spool(remote_id)
                assert refreshed["filament"]["price"] == 18.38
                assert refreshed["filament"]["spool_weight"] == 210

                # Same-diameter rebasing must not resurrect the older installed-nozzle profile.
                await _add_profile(
                    session,
                    product,
                    printer,
                    code="N04-OTHER",
                    diameter="0.4",
                    extruder="235",
                    bed="70",
                )
                printer.active_nozzle_id = nozzle.id
                printer.nozzle_diameter_mm = nozzle.diameter_mm
                spool.status = SpoolStatus.EMPTY
                await session.flush()
                await _converge_spoolman(session, client)
                await session.commit()
                refreshed = await client.get_spool(remote_id)
                assert refreshed["filament"].get("price") is None
                assert refreshed["filament"].get("settings_extruder_temp") is None
                assert refreshed["filament"].get("settings_bed_temp") is None
                assert refreshed["filament"]["name"] == "PLA · Blue · Silk"
                assert refreshed["comment"] == "SYNC-068 · PLA · Blue · Silk\nSpool notes"
                product.color_name = "Long color " * 8
                await session.flush()
                await _converge_spoolman(session, client)
                await session.commit()
                refreshed = await client.get_spool(remote_id)
                assert refreshed["filament"]["name"] == product.display_name[:64]
                assert refreshed["filament"]["comment"].startswith(product.display_name + "\n")
                assert refreshed["remaining_weight"] == 725
        finally:
            await engine.dispose()
