"""PostgreSQL-backed workstation pairing and deployment lifecycle tests."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api import dependencies
from filament_manager.api.routes import workstations
from filament_manager.config import Settings
from filament_manager.domain.cura_recovery import recovery_checksum
from filament_manager.domain.spool_preflight import cura_material_guid
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import CuraDeploymentStatus, ProfileStatus, UserRole
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Vendor,
)
from filament_manager.models.operations import AuditEvent
from filament_manager.models.workstations import (
    CuraDeployment,
    CuraManagedEditReceipt,
    CuraRecoveryRestore,
    CuraRecoverySnapshot,
    WorkstationAgent,
)
from filament_manager.security import create_agent_token, hash_password, hash_token


def test_combined_cura_import_source_count_prevents_automatic_takeover() -> None:
    """Saved print profiles block automatic takeover even without user materials."""

    assert (
        workstations._unmanaged_cura_source_count(
            {"unmanaged_material_count": 0, "unmanaged_import_source_count": 2}
        )
        == 2
    )
    assert workstations._unmanaged_cura_source_count({"unmanaged_material_count": 0}) == 0
    assert workstations._unmanaged_cura_source_count({"unmanaged_material_count": True}) is None


def test_agent_error_detail_is_bounded_to_safe_operator_guidance() -> None:
    """Heartbeat errors never expose a workstation path through the web API."""

    safe = "No Cura printer configuration was found to back up."
    assert workstations._sanitized_agent_error(safe) == safe
    assert workstations._sanitized_agent_error(None) is None
    assert workstations._sanitized_agent_error("Failed at /home/operator/private/Cura") == (
        "The workstation agent reported an error. Review its local service log."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pair_queue_claim_and_complete_workstation_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep enrollment one-time, credentials hashed, and deployment agent-scoped."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = Settings.model_validate(
            {
                "app": {
                    "base_url": "http://localhost",
                    "allowed_hosts": ["localhost"],
                    "secure_cookies": False,
                },
                "database": {"url": database_url},
                "spoolman": {"base_url": "http://spoolman.test:8000"},
                "moonraker": {
                    "printers": [
                        {
                            "id": "test-printer",
                            "name": "FLSUN V400",
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
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            administrator = User(
                username="workstation-admin",
                normalized_username="workstation-admin",
                display_name="Workstation Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            vendor = Vendor(name="Test Filament")
            printer = Printer(
                printer_code="flsun-v400",
                name="FLSUN V400",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add_all([administrator, vendor, printer])
            await session.flush()
            product = FilamentProduct(
                vendor_id=vendor.id,
                material_type="PETG",
                product_name="Workshop PETG",
                color_name="Black",
                filler=None,
                finish="Silk",
                color_hex="111111",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.27"),
                nominal_net_mass_g=Decimal("1000"),
            )
            session.add(product)
            await session.flush()
            template = MaterialTemplate(
                name="Template PETG",
                material_type="PETG",
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                filament_diameter_mm=Decimal("1.75"),
                active=True,
            )
            session.add(template)
            await session.flush()
            template_revision = MaterialTemplateRevision(
                material_template_id=template.id,
                version=1,
                status=ProfileStatus.PUBLISHED,
                settings={
                    "extruder_temp_c": "220",
                    "bed_temp_c": "70",
                    "flow_percent": "98",
                    "cooling_enabled": True,
                    "cooling_min_percent": "20",
                    "cooling_max_percent": "70",
                    "filament_density_g_cm3": "1.27",
                    "pressure_advance": "0.035",
                    "cura_extensions": {},
                },
                checksum="b" * 64,
                published_at=datetime.now(UTC),
            )
            session.add(template_revision)
            await session.flush()
            product.source_template_revision_id = template_revision.id
            profile = MaterialProfile(
                filament_product_id=product.id,
                printer_id=printer.id,
                nozzle_diameter_mm=Decimal("0.4"),
                version=1,
                status=ProfileStatus.PUBLISHED,
                extruder_temp_c=Decimal("220"),
                bed_temp_c=Decimal("70"),
                flow_percent=Decimal("98"),
                cooling_min_percent=Decimal("20"),
                cooling_max_percent=Decimal("70"),
                pressure_advance=Decimal("0.035"),
                filament_density_g_cm3=Decimal("1.27"),
                checksum="a" * 64,
                published_at=datetime.now(UTC),
                base_template_revision_id=template_revision.id,
                setting_overrides={},
            )
            session.add(profile)
            await session.commit()
            profile_id = profile.id

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "workstation-admin"))
                assert user is not None
                return user

        monkeypatch.setattr(workstations, "get_settings", lambda: settings)
        from filament_manager import config as config_module
        from filament_manager import main

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        monkeypatch.setattr(main, "get_settings", lambda: settings)
        application = main.create_app()
        application.dependency_overrides[dependencies.session_dependency] = session_override
        application.dependency_overrides[dependencies.current_user] = user_override

        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            code_response = await client.post("/api/v1/workstation-agents/pairing-codes")
            assert code_response.status_code == 201, code_response.text
            pairing_code = code_response.json()["pairing_code"]
            pair_response = await client.post(
                "/api/v1/workstation-agent/pair",
                json={
                    "pairing_code": pairing_code,
                    "display_name": "Arch Cura",
                    "hostname": "workshop-arch",
                    "platform": "arch_linux",
                    "architecture": "x86_64",
                    "agent_version": "0.1.0",
                    "capabilities": {
                        "atomic_install": True,
                        "unmanaged_material_count": 0,
                    },
                    "cura_installations": [
                        {
                            "installation_id": "cura-test",
                            "version": "5.13",
                            "channel": "Linux Cura",
                            "path_hint": "Linux Cura user data / 5.13",
                            "setting_version": 27,
                            "machines": [
                                {
                                    "machine_id": "flsun-v400",
                                    "display_name": "FLSUN V400",
                                    "definition_id": "flsun_v400",
                                    "nozzle_diameter_mm": "0.4",
                                }
                            ],
                        }
                    ],
                },
            )
            assert pair_response.status_code == 201, pair_response.text
            agent_token = pair_response.json()["agent_token"]
            replay = await client.post(
                "/api/v1/workstation-agent/pair",
                json={
                    "pairing_code": pairing_code,
                    "display_name": "Replay",
                    "hostname": "replay",
                    "platform": "arch_linux",
                    "architecture": "x86_64",
                    "agent_version": "0.1.0",
                },
            )
            assert replay.status_code == 401
            queued = await client.post(f"/api/v1/profiles/{profile_id}/deployments", json={})
            assert queued.status_code == 201, queued.text
            deployment_id = queued.json()[0]["id"]
            async with factory() as session:
                paired_agent = await session.scalar(select(WorkstationAgent))
                assert paired_agent is not None
                obsolete_failed = CuraDeployment(
                    agent_id=paired_agent.id,
                    material_profile_id=None,
                    requested_by=None,
                    status=CuraDeploymentStatus.FAILED,
                    payload={"schema_version": 3, "materials": []},
                    profile_checksum="f" * 64,
                    idempotency_key=f"obsolete-library:{paired_agent.id}",
                    attempts=1,
                    last_error_class="RuntimeError",
                    last_error_message="Old desired state failed",
                    next_attempt_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add(obsolete_failed)
                await session.commit()
                obsolete_failed_id = obsolete_failed.id
            claimed = await client.post(
                "/api/v1/workstation-agent/deployments/claim",
                headers={"Authorization": f"Bearer {agent_token}"},
            )
            assert claimed.status_code == 200, claimed.text
            assert claimed.json()["deployment_id"] == deployment_id
            assert claimed.json()["payload"]["schema_version"] == 3
            assert claimed.json()["payload"]["hide_bundled_materials"] is True
            claimed_product = next(
                material
                for material in claimed.json()["payload"]["materials"]
                if material["source_kind"] == "product"
            )
            assert claimed_product["material"]["filler"] is None
            assert claimed_product["material"]["finish"] == "Silk"
            completed = await client.post(
                f"/api/v1/workstation-agent/deployments/{deployment_id}/complete",
                headers={"Authorization": f"Bearer {agent_token}"},
                json={"outcome": "succeeded", "result": {"managed_files": 4}},
            )
            assert completed.status_code == 204, completed.text
            edited = await client.post(
                "/api/v1/workstation-agent/heartbeat",
                headers={"Authorization": f"Bearer {agent_token}"},
                json={
                    "agent_version": "0.2.0",
                    "capabilities": {
                        "atomic_install": True,
                        "unmanaged_material_count": 0,
                    },
                    "cura_installations": [
                        {
                            "installation_id": "cura-test",
                            "version": "5.13",
                            "channel": "Linux Cura",
                            "path_hint": "Linux Cura user data / 5.13",
                            "setting_version": 27,
                            "managed_library_checksum": "a" * 64,
                            "material_settings_sync": {
                                "status": "healthy",
                                "expected_count": 54,
                                "exposed_count": 54,
                                "missing_keys": [],
                                "unexpected_keys": [],
                                "material_settings_plugin_ready": True,
                                "klipper_settings_plugin_ready": True,
                                "plugins": [
                                    {
                                        "role": "material_settings",
                                        "package_id": "MaterialSettingsPlugin",
                                        "display_name": "Material Settings",
                                        "version": "4.3.1",
                                        "enabled": True,
                                    },
                                    {
                                        "role": "klipper_settings",
                                        "package_id": "KlipperSettingsPlugin",
                                        "display_name": "Klipper Settings Plugin",
                                        "version": "1.0.2",
                                        "enabled": True,
                                    },
                                ],
                                "catalog_checksum": "b" * 64,
                                "verified_at": "2026-08-22T04:00:00Z",
                            },
                            "machines": [],
                        }
                    ],
                    "cura_managed_materials": [
                        {
                            "source_id": "c" * 64,
                            "installation_id": "cura-test",
                            "name": "Test Filament PETG · Black",
                            "brand": "Test Filament",
                            "material_type": "PETG",
                            "color_name": "Black",
                            "material_guid": cura_material_guid("product", profile_id),
                            "content_checksum": "d" * 64,
                            "settings": {
                                "material_print_temperature": "225",
                                "material_bed_temperature": "70",
                                "material_flow": "98",
                                "cool_fan_enabled": True,
                                "cool_fan_speed_min": "20",
                                "cool_fan_speed_max": "70",
                                "klipper_pressure_advance_factor": "0.035",
                            },
                        }
                    ],
                },
            )
            assert edited.status_code == 204, edited.text
            edited_again = await client.post(
                "/api/v1/workstation-agent/heartbeat",
                headers={"Authorization": f"Bearer {agent_token}"},
                json=json.loads(edited.request.content),
            )
            assert edited_again.status_code == 204, edited_again.text

        async with factory() as session:
            agent = await session.scalar(select(WorkstationAgent))
            assert agent is not None
            assert agent.token_hash != agent_token
            assert agent.cura_installations[0]["material_settings_sync"] == {
                "status": "healthy",
                "expected_count": 54,
                "exposed_count": 54,
                "missing_keys": [],
                "unexpected_keys": [],
                "material_settings_plugin_ready": True,
                "klipper_settings_plugin_ready": True,
                "plugins": [
                    {
                        "role": "material_settings",
                        "package_id": "MaterialSettingsPlugin",
                        "display_name": "Material Settings",
                        "version": "4.3.1",
                        "enabled": True,
                    },
                    {
                        "role": "klipper_settings",
                        "package_id": "KlipperSettingsPlugin",
                        "display_name": "Klipper Settings Plugin",
                        "version": "1.0.2",
                        "enabled": True,
                    },
                ],
                "catalog_checksum": "b" * 64,
                "verified_at": "2026-08-22T04:00:00Z",
            }
            deployment = await session.get(CuraDeployment, deployment_id)
            assert deployment is not None
            assert deployment.status == CuraDeploymentStatus.SUCCEEDED
            obsolete_failed = await session.get(CuraDeployment, obsolete_failed_id)
            assert obsolete_failed is not None
            assert obsolete_failed.status == CuraDeploymentStatus.CANCELLED
            queued_current_library = await session.scalar(
                select(CuraDeployment)
                .where(CuraDeployment.id != deployment_id)
                .order_by(CuraDeployment.created_at.desc())
                .limit(1)
            )
            assert queued_current_library is not None
            assert queued_current_library.status == CuraDeploymentStatus.PENDING
            current_profile = await session.scalar(
                select(MaterialProfile)
                .where(MaterialProfile.filament_product_id == profile.filament_product_id)
                .order_by(MaterialProfile.version.desc())
                .limit(1)
            )
            assert current_profile is not None and current_profile.version == 2
            assert current_profile.status == ProfileStatus.PUBLISHED
            assert current_profile.extruder_temp_c == Decimal("225.00000")
            assert current_profile.base_template_revision_id == template_revision.id
            receipt = await session.scalar(select(CuraManagedEditReceipt))
            assert receipt is not None
            assert receipt.content_checksum != "d" * 64
            assert await session.scalar(select(func.count(CuraManagedEditReceipt.id))) == 1
            assert await session.scalar(select(func.count(AuditEvent.id))) == 5

        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cura_recovery_snapshot_and_restore_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retain sanitized exact-version snapshots and lease confirmed restores."""

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        settings = Settings.model_validate(
            {
                "app": {
                    "base_url": "http://localhost",
                    "allowed_hosts": ["localhost"],
                    "secure_cookies": False,
                },
                "database": {"url": database_url},
                "spoolman": {"base_url": "http://spoolman.test:8000"},
                "moonraker": {
                    "printers": [
                        {
                            "id": "test-printer",
                            "name": "Workshop Printer",
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
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        agent_token = create_agent_token()
        async with factory() as session:
            administrator = User(
                username="recovery-admin",
                normalized_username="recovery-admin",
                display_name="Recovery Administrator",
                password_hash=hash_password("integration test password"),
                role=UserRole.ADMINISTRATOR,
            )
            session.add(administrator)
            await session.flush()
            printer = Printer(
                printer_code="workshop-printer",
                name="Workshop Printer",
                moonraker_base_url="http://moonraker.test:7125",
                nozzle_diameter_mm=Decimal("0.4"),
            )
            session.add(printer)
            agent = WorkstationAgent(
                agent_code="WS-RECOVERYTEST",
                display_name="Recovery Cura",
                hostname="recovery-workstation",
                platform="arch_linux",
                architecture="x86_64",
                agent_version="0.2.4",
                token_hash=hash_token(agent_token),
                enabled=True,
                cura_management_enabled=True,
                capabilities={"cura_recovery_snapshots": True},
                cura_installations=[
                    {
                        "installation_id": "cura-test",
                        "version": "5.13",
                        "channel": "Linux Cura",
                        "path_hint": "Linux Cura user data / 5.13",
                        "setting_version": 27,
                        "machines": [
                            {
                                "machine_id": "workshop",
                                "display_name": "Workshop Printer",
                            }
                        ],
                    }
                ],
                cura_materials=[],
                created_by=administrator.id,
            )
            session.add(agent)
            await session.commit()
            agent_id = agent.id

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def user_override() -> User:
            async with factory() as session:
                user = await session.scalar(select(User).where(User.username == "recovery-admin"))
                assert user is not None
                return user

        monkeypatch.setattr(workstations, "get_settings", lambda: settings)
        from filament_manager import config as config_module
        from filament_manager import main

        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        monkeypatch.setattr(main, "get_settings", lambda: settings)
        application = main.create_app()
        application.dependency_overrides[dependencies.session_dependency] = session_override
        application.dependency_overrides[dependencies.current_user] = user_override
        transport = httpx.ASGITransport(app=application)
        snapshot_payload: dict[str, object] = {
            "schema_version": 1,
            "installation_id": "cura-test",
            "cura_version": "5.13",
            "setting_version": 27,
            "files": [
                {
                    "scope": "data",
                    "relative_path": "machine_instances/Workshop.global.cfg",
                    "content": "[general]\nname = Workshop Printer\n",
                },
                {
                    "scope": "config",
                    "relative_path": "cura.cfg",
                    "content": "[general]\ntheme = dark\n\n[cura]\nactive_machine = workshop\n",
                },
            ],
            "plugins": [
                {
                    "package_id": "MaterialSettingsPlugin",
                    "display_name": "Material Settings",
                    "version": "4.3.1",
                    "enabled": True,
                }
            ],
        }
        checksum = recovery_checksum(snapshot_payload)

        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            headers = {"Authorization": f"Bearer {agent_token}"}
            uploaded = await client.post(
                "/api/v1/workstation-agent/cura-recovery-snapshots",
                headers=headers,
                json={"snapshot_checksum": checksum, "payload": snapshot_payload},
            )
            assert uploaded.status_code == 200, uploaded.text
            assert uploaded.json()["accepted"] is True
            snapshot_id = uploaded.json()["snapshot_id"]
            duplicate = await client.post(
                "/api/v1/workstation-agent/cura-recovery-snapshots",
                headers=headers,
                json={"snapshot_checksum": checksum, "payload": snapshot_payload},
            )
            assert duplicate.status_code == 200, duplicate.text
            assert duplicate.json()["snapshot_id"] == snapshot_id

            capture_request = await client.post(
                f"/api/v1/workstation-agents/{agent_id}/cura-recovery-captures",
                json={
                    "installation_id": "cura-test",
                    "name": "Before nozzle change",
                    "description": "Known-good workshop configuration",
                },
            )
            assert capture_request.status_code == 202, capture_request.text
            assert capture_request.json()["operation"] == "recovery_capture"
            capture_deployment_id = capture_request.json()["id"]
            claimed_capture = await client.post(
                "/api/v1/workstation-agent/deployments/claim",
                headers=headers,
            )
            assert claimed_capture.status_code == 200, claimed_capture.text
            assert claimed_capture.json()["deployment_id"] == capture_deployment_id
            manual = await client.post(
                "/api/v1/workstation-agent/cura-recovery-snapshots",
                headers=headers,
                json={
                    "snapshot_checksum": checksum,
                    "payload": snapshot_payload,
                    "capture_request_id": capture_deployment_id,
                },
            )
            assert manual.status_code == 200, manual.text
            assert manual.json()["snapshot_id"] != snapshot_id
            manual_snapshot_id = manual.json()["snapshot_id"]
            capture_completed = await client.post(
                f"/api/v1/workstation-agent/deployments/{capture_deployment_id}/complete",
                headers=headers,
                json={
                    "outcome": "succeeded",
                    "result": {"snapshot_id": manual_snapshot_id, "installation_id": "cura-test"},
                },
            )
            assert capture_completed.status_code == 204, capture_completed.text
            manual_list = await client.get(f"/api/v1/workstation-agents/{agent_id}/cura-recovery-snapshots")
            manual_item = next(item for item in manual_list.json() if item["id"] == manual_snapshot_id)
            assert manual_item["capture_kind"] == "manual"
            assert manual_item["name"] == "Before nozzle change"
            renamed = await client.patch(
                f"/api/v1/workstation-agents/{agent_id}/cura-recovery-snapshots/{manual_snapshot_id}",
                json={
                    "expected_version": manual_item["record_version"],
                    "name": "Before 0.6 mm nozzle",
                    "description": "Ready to restore",
                },
            )
            assert renamed.status_code == 200, renamed.text
            assert renamed.json()["name"] == "Before 0.6 mm nozzle"
            deleted = await client.request(
                "DELETE",
                f"/api/v1/workstation-agents/{agent_id}/cura-recovery-snapshots/{manual_snapshot_id}",
                json={"expected_version": renamed.json()["record_version"], "confirmed": True},
            )
            assert deleted.status_code == 204, deleted.text

            reset_payload = {
                **snapshot_payload,
                "files": [
                    {
                        "scope": "config",
                        "relative_path": "cura.cfg",
                        "content": "[general]\ntheme = light\n",
                    }
                ],
            }
            blocked = await client.post(
                "/api/v1/workstation-agent/cura-recovery-snapshots",
                headers=headers,
                json={
                    "snapshot_checksum": recovery_checksum(reset_payload),
                    "payload": reset_payload,
                },
            )
            assert blocked.status_code == 200, blocked.text
            assert blocked.json()["accepted"] is False
            assert blocked.json()["reason"] == "no_printer_configuration"

            snapshots = await client.get(f"/api/v1/workstation-agents/{agent_id}/cura-recovery-snapshots")
            assert snapshots.status_code == 200, snapshots.text
            assert len(snapshots.json()) == 1
            assert snapshots.json()[0]["plugin_count"] == 1
            assert "payload" not in snapshots.json()[0]

            queued = await client.post(
                f"/api/v1/workstation-agents/{agent_id}/cura-recovery-restores",
                json={"snapshot_id": snapshot_id, "confirmed": True},
            )
            assert queued.status_code == 201, queued.text
            restore_id = queued.json()["id"]
            claimed = await client.post(
                "/api/v1/workstation-agent/cura-recovery-restores/claim",
                headers=headers,
            )
            assert claimed.status_code == 200, claimed.text
            assert claimed.json()["restore_id"] == restore_id
            completed = await client.post(
                f"/api/v1/workstation-agent/cura-recovery-restores/{restore_id}/complete",
                headers=headers,
                json={
                    "outcome": "succeeded",
                    "result": {
                        "installation_id": "cura-test",
                        "version": "5.13",
                        "status": "restored",
                        "restored_files": 2,
                        "removed_files": 1,
                        "preferences_merged": True,
                        "backup_id": f"{restore_id}/cura-test",
                        "missing_plugins": [],
                    },
                },
            )
            assert completed.status_code == 204, completed.text

            for index in range(10):
                retained_payload = {
                    **snapshot_payload,
                    "files": [
                        snapshot_payload["files"][0],  # type: ignore[index]
                        {
                            "scope": "config",
                            "relative_path": "cura.cfg",
                            "content": (
                                f"[general]\ntheme = retained-{index}\n\n[cura]\nactive_machine = workshop\n"
                            ),
                        },
                    ],
                }
                retained_checksum = recovery_checksum(retained_payload)
                retained = await client.post(
                    "/api/v1/workstation-agent/cura-recovery-snapshots",
                    headers=headers,
                    json={
                        "snapshot_checksum": retained_checksum,
                        "payload": retained_payload,
                    },
                )
                assert retained.status_code == 200, retained.text
                assert retained.json()["accepted"] is True

            retained_snapshots = await client.get(
                f"/api/v1/workstation-agents/{agent_id}/cura-recovery-snapshots"
            )
            assert retained_snapshots.status_code == 200, retained_snapshots.text
            assert len(retained_snapshots.json()) == 10
            assert snapshot_id not in {item["id"] for item in retained_snapshots.json()}
            deleted_automatic = next(
                item for item in retained_snapshots.json() if item["snapshot_checksum"] == retained_checksum
            )
            deleted = await client.request(
                "DELETE",
                f"/api/v1/workstation-agents/{agent_id}/cura-recovery-snapshots/{deleted_automatic['id']}",
                json={
                    "expected_version": deleted_automatic["record_version"],
                    "confirmed": True,
                },
            )
            assert deleted.status_code == 204, deleted.text
            suppressed = await client.post(
                "/api/v1/workstation-agent/cura-recovery-snapshots",
                headers=headers,
                json={
                    "snapshot_checksum": retained_checksum,
                    "payload": retained_payload,
                },
            )
            assert suppressed.status_code == 200, suppressed.text
            assert suppressed.json()["accepted"] is False
            assert suppressed.json()["reason"] == "deleted_by_administrator"

        async with factory() as session:
            assert await session.scalar(select(func.count(CuraRecoverySnapshot.id))) == 9
            restore = await session.get(CuraRecoveryRestore, restore_id)
            assert restore is not None and restore.status == CuraDeploymentStatus.SUCCEEDED
            assert restore.snapshot_id is None
            assert restore.snapshot_checksum == checksum
            agent = await session.get(WorkstationAgent, agent_id)
            assert agent is not None
            assert agent.cura_recovery_status == "ready"
            assert agent.last_recovery_restore_at is not None
            assert len(agent.suppressed_recovery_snapshots) == 1
            nozzle_alignment = await session.scalar(
                select(CuraDeployment).where(
                    CuraDeployment.agent_id == agent_id,
                    CuraDeployment.idempotency_key.like(f"%recovery-{restore_id}"),
                )
            )
            assert nozzle_alignment is not None
            assert nozzle_alignment.payload["operation"] == "nozzle_update"
            assert Decimal(str(nozzle_alignment.payload["nozzle_diameter_mm"])) == Decimal("0.4")

        await engine.dispose()
