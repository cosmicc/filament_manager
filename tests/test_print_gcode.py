"""Exact file retention, bounded serving, and idle-only stale history recovery."""

import hashlib
import zlib
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from filament_manager.api.errors import ApiError
from filament_manager.api.routes import printing
from filament_manager.api.schemas import CloseStalePrintRequest
from filament_manager.clients import moonraker
from filament_manager.clients.moonraker import MoonrakerError
from filament_manager.config import PrinterConfig
from filament_manager.models import Base
from filament_manager.models.enums import PrintJobStatus
from filament_manager.models.inventory import Printer
from filament_manager.models.printing import PrintGcodeArchive, PrintJob
from filament_manager.services.print_gcode import archive_bytes


@pytest.mark.asyncio
async def test_one_download_archives_exact_bytes_and_discards_oversized_copy(monkeypatch) -> None:
    """Retention uses the existing hashed stream and never stores partial originals."""
    data = b";original\r\nG1 X1\n" * 100
    client_type = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=data)

    monkeypatch.setattr(
        moonraker.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs),
    )
    configured = PrinterConfig(
        id="test",
        name="Test",
        base_url="http://moonraker.test",
        websocket_url="ws://moonraker.test/websocket",
        nozzle_diameter_mm=0.4,
    )
    result = await moonraker.MoonrakerClient(configured).gcode_file("sample.gcode")
    assert zlib.decompress(result.compressed_data) == data
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert len(requests) == 1
    monkeypatch.setattr(moonraker, "MAX_GCODE_ARCHIVE_BYTES", 10)
    result = await moonraker.MoonrakerClient(configured).gcode_file("sample.gcode")
    assert result.compressed_data is None
    assert result.sha256 == hashlib.sha256(data).hexdigest()


def test_archive_integrity_and_decompression_limits() -> None:
    """Reject tampered digests, truncated/trailing streams and inflated sizes."""
    data = b";private original\r\nG1 X1\n"
    archive = PrintGcodeArchive(
        print_job_id=uuid4(),
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        compressed_data=zlib.compress(data),
    )
    assert archive_bytes(archive) == data
    for compressed, size, digest in [
        (zlib.compress(data)[:-1], len(data), archive.sha256),
        (zlib.compress(data) + b"trailing", len(data), archive.sha256),
        (zlib.compress(data), 1, archive.sha256),
        (zlib.compress(data), 100_000_001, archive.sha256),
        (zlib.compress(data), len(data), "0" * 64),
    ]:
        with pytest.raises(ValueError):
            archive_bytes(PrintGcodeArchive(size_bytes=size, compressed_data=compressed, sha256=digest))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_archive_routes_and_idle_only_closure(monkeypatch) -> None:
    """Prove exact database readback and no fabricated usage/end time on closure."""
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        engine = create_async_engine(postgres.get_connection_url())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            printer = Printer(
                printer_code="test",
                name="Test",
                nozzle_diameter_mm=Decimal("0.4"),
                moonraker_base_url="http://moonraker.test:7125",
            )
            session.add(printer)
            await session.flush()
            job = PrintJob(
                printer_id=printer.id,
                filename="original.gcode",
                status=PrintJobStatus.IN_PROGRESS,
                started_at=datetime.now(UTC),
                state_snapshot={"exact": "preserved"},
            )
            session.add(job)
            await session.flush()
            data = b"G1 X1\r\n" * 6000
            session.add(
                PrintGcodeArchive(
                    print_job_id=job.id,
                    sha256=hashlib.sha256(data).hexdigest(),
                    size_bytes=len(data),
                    compressed_data=zlib.compress(data),
                )
            )
            await session.commit()
            response = await printing.get_print_gcode(job.id, None, session, page=1, download=True)
            assert response.body == data
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["cache-control"] == "no-store"
            page = await printing.get_print_gcode(job.id, None, session, page=2, download=False)
            assert b'"page":2' in page.body
            with pytest.raises(ApiError, match="No verified"):
                await printing.get_print_gcode(uuid4(), None, session, page=1, download=False)

            async def connections(*args):
                return [SimpleNamespace(id="test")]

            live_state = "printing"

            class Client:
                def __init__(self, *args):
                    pass

                async def print_state(self):
                    if live_state == "offline":
                        raise MoonrakerError("unavailable")
                    return SimpleNamespace(state=live_state)

                async def gcode_file(self, filename, **kwargs):
                    assert filename == "reused.gcode"
                    assert kwargs["max_bytes"] == 100_000_000
                    return SimpleNamespace(
                        sha256=hashlib.sha256(data).hexdigest(),
                        size=len(data),
                        compressed_data=zlib.compress(data),
                        header=';FM_CURA_PROFILE_JSON:"Fine"\n',
                        tail="",
                    )

            monkeypatch.setattr(printing, "configured_printers", connections)
            monkeypatch.setattr(printing, "MoonrakerClient", Client)
            request = SimpleNamespace(state=SimpleNamespace(correlation_id="test-close"))
            actor = SimpleNamespace(id=None)
            for state in ("printing", "paused", "offline"):
                live_state = state
                with pytest.raises(ApiError):
                    await printing.close_stale_print(
                        job.id, CloseStalePrintRequest(expected_version=1), actor, session, request
                    )
                assert job.status == PrintJobStatus.IN_PROGRESS
            live_state = "standby"
            with pytest.raises(ApiError):
                await printing.close_stale_print(
                    job.id, CloseStalePrintRequest(expected_version=2), actor, session, request
                )
            await printing.close_stale_print(
                job.id, CloseStalePrintRequest(expected_version=1), actor, session, request
            )
            await session.refresh(job)
            assert job.status == PrintJobStatus.LEGACY_UNKNOWN
            assert job.ended_at is None
            assert job.actual_filament_weight_g is None
            assert job.state_snapshot["exact"] == "preserved"
            assert await session.scalar(select(PrintGcodeArchive.print_job_id)) == job.id
            legacy = PrintJob(
                printer_id=printer.id,
                filename="reused.gcode",
                status=PrintJobStatus.COMPLETED,
                gcode_sha256="a" * 64,
                started_at=datetime.now(UTC),
            )
            session.add(legacy)
            await session.commit()
            with pytest.raises(ApiError, match="no longer matches"):
                await printing.capture_verified_print_gcode(legacy.id, actor, session)
            assert await session.get(PrintGcodeArchive, legacy.id) is None
            legacy.gcode_sha256 = hashlib.sha256(data).hexdigest()
            await session.commit()
            assert await printing.capture_verified_print_gcode(legacy.id, actor, session) == {"saved": True}
            saved = await session.get(PrintGcodeArchive, legacy.id)
            assert saved is not None and archive_bytes(saved) == data
            assert legacy.cura_quality_profile == "Fine"
        await engine.dispose()


@pytest.mark.asyncio
async def test_archive_and_history_repair_require_browser_authorization() -> None:
    """Anonymous reads and writes fail; read-only accounts cannot repair history."""
    from fastapi import FastAPI

    from filament_manager.api import dependencies
    from filament_manager.api.errors import api_error_handler
    from filament_manager.models.enums import UserRole

    async def no_database():
        yield None

    async def viewer():
        return SimpleNamespace(role=UserRole.VIEWER)

    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(printing.router, prefix="/api/v1")
    app.dependency_overrides[dependencies.session_dependency] = no_database
    print_id = uuid4()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get(f"/api/v1/prints/{print_id}/gcode")).status_code == 401
        assert (
            await client.post(f"/api/v1/prints/{print_id}/close-stale", json={"expected_version": 1})
        ).status_code == 401
        app.dependency_overrides[dependencies.current_user] = viewer
        assert (
            await client.post(f"/api/v1/prints/{print_id}/close-stale", json={"expected_version": 1})
        ).status_code == 403
        assert (await client.post(f"/api/v1/prints/{print_id}/gcode/capture")).status_code == 403
