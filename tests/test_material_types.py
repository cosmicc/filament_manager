"""Real PostgreSQL regression coverage for global material-type correction."""

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Nozzle,
    Printer,
    Spool,
)
from filament_manager.models.operations import AuditEvent, OutboxJob
from filament_manager.services.material_settings import create_published_profile_snapshot


@pytest.mark.integration
@pytest.mark.asyncio
async def test_global_material_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rename every scope/archive with exact history, duplicate and stale-write protection."""
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
                printer_code="types",
                name="Types",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add_all([user, printer])
            await session.flush()
            nozzles = [
                Nozzle(
                    nozzle_code=f"N{i}",
                    printer_id=printer.id,
                    diameter_mm=Decimal(diameter),
                    material="Brass",
                )
                for i, diameter in enumerate(("0.4", "0.6"))
            ]
            session.add_all(nozzles)
            await session.commit()

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            return user

        from filament_manager import config, main
        from filament_manager.api.routes import inventory
        from filament_manager.services import events

        for module in (config, main, inventory, events):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        app.dependency_overrides[dependencies.current_user] = user_override
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            endpoint = "/api/v1/profiles/material-types"
            assert (await client.get(endpoint)).status_code == 200
            for bad in ("", " ", "x" * 49, "ASA\nCF"):
                assert (await client.post(endpoint, json={"name": bad})).status_code == 422
            created = await client.post(endpoint, json={"name": "  PLA Carbon Fiber  "})
            assert created.status_code == 201, created.text
            item = created.json()
            assert (await client.post(endpoint, json={"name": "pla carbon fiber"})).status_code == 409
            assert (await client.post(endpoint, json={"name": "ASA-CF"})).status_code == 201
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(MaterialTemplate)) == 0
            for nozzle in nozzles:
                response = await client.post(
                    "/api/v1/profiles/templates",
                    json={
                        "name": "unused",
                        "material_type": "PLA Carbon Fiber",
                        "printer_id": str(printer.id),
                        "nozzle_id": str(nozzle.id),
                        "nozzle_diameter_mm": str(nozzle.diameter_mm),
                        "filament_diameter_mm": "1.75",
                        "settings": {
                            "filament_density_g_cm3": "1.24",
                            "bed_temp_c": "60",
                            "extruder_temp_c": "220",
                            "flow_percent": "100",
                            "cooling_min_percent": "30",
                            "cooling_max_percent": "100",
                        },
                    },
                )
                assert response.status_code == 201, response.text
            async with factory() as session:
                templates = list(await session.scalars(select(MaterialTemplate)))
                revisions = list(await session.scalars(select(MaterialTemplateRevision)))
                revision_evidence = [(r.id, r.settings, r.checksum) for r in revisions]
                product = FilamentProduct(
                    material_type="PLA Carbon Fiber",
                    color_name="Black",
                    diameter_mm=Decimal("1.75"),
                    density_g_cm3=Decimal("1.24"),
                    nominal_net_mass_g=Decimal("1000"),
                    archived=True,
                )
                session.add(product)
                await session.flush()
                retained_profiles = []
                for template in templates:
                    base = next(r for r in revisions if r.material_template_id == template.id)
                    profile = await create_published_profile_snapshot(
                        session,
                        filament_product_id=product.id,
                        printer_id=printer.id,
                        nozzle_diameter_mm=template.nozzle_diameter_mm,
                        base_revision=base,
                        settings={**base.settings, "bed_temp_c": "75"},
                        setting_overrides={"bed_temp_c": "75"},
                    )
                    retained_profiles.append((profile.id, profile.checksum, dict(profile.setting_overrides)))
                spool = Spool(
                    filament_product_id=product.id,
                    spool_code="PCF1",
                    nominal_net_mass_g=Decimal("1000"),
                    tare_mass_g=Decimal("200"),
                    remaining_mass_expected_g=Decimal("700"),
                    remaining_mass_effective_g=Decimal("700"),
                )
                session.add(spool)
                await session.commit()
                product_id, spool_id = product.id, spool.id
            payload = {
                "name": "PLA-CF",
                "confirmation_name": item["name"],
                "expected_version": item["record_version"],
            }
            assert (
                await client.put(f"{endpoint}/{item['id']}", json={**payload, "confirmation_name": "wrong"})
            ).status_code == 422
            assert (
                await client.put(f"{endpoint}/{item['id']}", json={**payload, "name": "asa-cf"})
            ).status_code == 409
            renamed = await client.put(f"{endpoint}/{item['id']}", json=payload)
            assert renamed.status_code == 200, renamed.text
            assert renamed.json()["record_version"] == 2
            assert (await client.put(f"{endpoint}/{item['id']}", json=payload)).status_code == 409
            async with factory() as session:
                assert [
                    (r.id, r.settings, r.checksum)
                    for r in await session.scalars(select(MaterialTemplateRevision))
                ] == revision_evidence
                current = list(await session.scalars(select(MaterialTemplate)))
                assert {t.id for t in current} == {t.id for t in templates}
                assert all(t.material_type == "PLA-CF" and t.name == "Template PLA-CF" for t in current)
                product = await session.get(FilamentProduct, product_id)
                assert product and product.material_type == "PLA-CF" and product.archived
                spool = await session.get(Spool, spool_id)
                assert (
                    spool
                    and spool.spool_code == "PCF1"
                    and spool.remaining_mass_effective_g == Decimal("700")
                )
                jobs = list(await session.scalars(select(OutboxJob)))
                assert any(
                    j.job_type == "spoolman.filament.upsert" and j.aggregate_id == product_id for j in jobs
                )
                assert any(j.job_type == "spoolman.spool.upsert" and j.aggregate_id == spool_id for j in jobs)
                assert any(j.job_type == "google.publish.pending" for j in jobs)
                assert await session.scalar(
                    select(AuditEvent.id).where(AuditEvent.action == "material_type.rename")
                )
                assert [
                    (p.id, p.checksum, dict(p.setting_overrides))
                    for p in await session.scalars(select(MaterialProfile))
                ] == retained_profiles
            concurrent = await asyncio.gather(
                *[
                    client.put(
                        f"{endpoint}/{item['id']}",
                        json={"name": "PLA-CF2", "confirmation_name": "PLA-CF", "expected_version": 2},
                    )
                    for _ in range(2)
                ]
            )
            assert sorted(response.status_code for response in concurrent) == [200, 409]
            delete_payload = {"confirmation_name": "PLA-CF2", "expected_version": 3}
            delete_path = f"{endpoint}/{item['id']}"
            assert (
                await client.request("DELETE", delete_path, json={**delete_payload, "expected_version": 2})
            ).status_code == 409
            assert (
                await client.request(
                    "DELETE", delete_path, json={**delete_payload, "confirmation_name": "wrong"}
                )
            ).status_code == 422
            blocked = await client.request("DELETE", delete_path, json=delete_payload)
            assert blocked.status_code == 409 and blocked.json()["code"] == "material_type_in_use"
            async with factory() as session:
                matching = list(await session.scalars(select(MaterialTemplate)))
                # An active case-equivalent scope still protects the choice.
                matching[0].active = False
                matching[1].material_type = "pla-cf2"
                await session.commit()
            assert (await client.request("DELETE", delete_path, json=delete_payload)).status_code == 409
            async with factory() as session:
                for template in await session.scalars(select(MaterialTemplate)):
                    template.active = False
                await session.commit()
            deleted = await client.request("DELETE", delete_path, json=delete_payload)
            assert deleted.status_code == 200, deleted.text
            assert (await client.request("DELETE", delete_path, json=delete_payload)).status_code == 404
            assert not any(value["id"] == item["id"] for value in (await client.get(endpoint)).json())
            async with factory() as session:
                from filament_manager.services.material_types import (
                    remember_material_type,
                    seeded_material_type_name,
                )

                assert await remember_material_type(session, "PLA-CF2") is None
                assert await seeded_material_type_name(session, "PLA-CF2") is None
                # The original seed identity was renamed and then removed.
                assert await seeded_material_type_name(session, "PLA-CF") is None
                current_product = await session.get(FilamentProduct, product_id)
                assert (
                    current_product
                    and current_product.material_type == "PLA-CF2"
                    and current_product.archived
                )
                assert [
                    (p.id, p.checksum, dict(p.setting_overrides))
                    for p in await session.scalars(select(MaterialProfile))
                ] == retained_profiles
                assert [
                    (r.id, r.settings, r.checksum)
                    for r in await session.scalars(select(MaterialTemplateRevision))
                ] == revision_evidence
                audit = await session.scalar(
                    select(AuditEvent).where(AuditEvent.action == "material_type.delete")
                )
                assert audit and audit.before["name"] == "PLA-CF2"
                assert await session.scalar(
                    select(OutboxJob.id).where(
                        OutboxJob.idempotency_key == f"material-type:{item['id']}:delete:v3"
                    )
                )
            recreated = await client.post(endpoint, json={"name": "PLA-CF2"})
            assert recreated.status_code == 201 and recreated.json()["id"] != item["id"]
            async with factory() as session:
                assert await remember_material_type(session, "PLA-CF2") is not None
                assert await seeded_material_type_name(session, "PLA-CF2") == "PLA-CF2"
            # Deletion and a new scope creator share the catalog lock.
            async with factory() as session:
                from filament_manager.models.inventory import MaterialType
                from filament_manager.services.material_types import lock_material_types

                await lock_material_types(session)
                created_item = await session.get(MaterialType, recreated.json()["id"])
                assert created_item is not None
                waiting_delete = asyncio.create_task(
                    client.request(
                        "DELETE",
                        f"{endpoint}/{created_item.id}",
                        json={"confirmation_name": created_item.name, "expected_version": 1},
                    )
                )
                template = await session.get(MaterialTemplate, templates[0].id)
                assert template is not None
                template.material_type = "PLA-CF2"
                template.active = True
                await session.commit()
                assert (await waiting_delete).status_code == 409

            user.role = UserRole.VIEWER
            assert (await client.post(endpoint, json={"name": "Denied"})).status_code == 403
            assert (await client.put(f"{endpoint}/{item['id']}", json=payload)).status_code == 403
            assert (await client.request("DELETE", delete_path, json=delete_payload)).status_code == 403
            app.dependency_overrides.pop(dependencies.current_user)
            assert (await client.get(endpoint)).status_code == 401
            assert (await client.request("DELETE", delete_path, json=delete_payload)).status_code == 401
        await engine.dispose()
