"""Google contracts, security boundaries, and real PostgreSQL publication tests."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from googleapiclient.discovery_cache import get_static_doc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager.clients import google_workbook as google_http
from filament_manager.clients.google_sheets import GoogleSheetsError
from filament_manager.clients.google_workbook import GoogleWorkbookClient
from filament_manager.models import Base
from filament_manager.models.auth import User, UserSession
from filament_manager.models.enums import UserRole
from filament_manager.models.google import GoogleConnection
from filament_manager.models.inventory import FilamentProduct
from filament_manager.security import hash_token
from filament_manager.services import google_connection, google_publication
from filament_manager.services import google_workbook as google_export
from filament_manager.services.google_workbook import (
    EXPORTS,
    WorkbookTab,
    cell,
    fingerprint,
    flatten,
    snapshot,
)


def validate_google_request(value: object, schema: dict[str, object], schemas: dict[str, object]) -> None:
    """Validate actual outgoing bodies against the bundled official discovery schema."""
    if "$ref" in schema:
        validate_google_request(value, schemas[schema["$ref"]], schemas)
        return
    kind = schema.get("type")
    if kind == "object":
        assert isinstance(value, dict)
        properties = schema.get("properties", {})
        for key, item in value.items():
            assert key in properties or "additionalProperties" in schema, f"Unknown Google field: {key}"
            validate_google_request(item, properties.get(key, schema.get("additionalProperties")), schemas)
    elif kind == "array":
        assert isinstance(value, list)
        for item in value:
            validate_google_request(item, schema["items"], schemas)
    elif kind == "string":
        assert isinstance(value, str)
        if "enum" in schema:
            assert value in schema["enum"]
    elif kind == "integer":
        assert type(value) is int
    elif kind == "number":
        assert type(value) in (int, float)
    elif kind == "boolean":
        assert isinstance(value, bool)


def test_export_contract_and_inert_values() -> None:
    """Schema additions never silently export secrets; formulas remain literal."""
    for _title, table, fields in EXPORTS:
        assert set(fields.split()) <= set(Base.metadata.tables[table].c.keys())
        assert table not in {"users", "google_connection", "workstation_agents", "application_settings"}
    assert cell('=IMPORTXML("https://example.invalid","//x")')["userEnteredValue"].keys() == {"stringValue"}
    assert cell(False)["userEnteredValue"] == {"boolValue": False}
    assert flatten({"retraction": 2, "api_key": "private", "nested": {"host": "internal"}}) == [
        ("api_key", "[excluded: security or connection field]"),
        ("nested.host", "[excluded: security or connection field]"),
        ("retraction", 2),
    ]


@pytest.mark.asyncio
async def test_google_request_pacing_and_sanitized_denial(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply quota headroom between requests and never expose Google's error body."""
    waits: list[float] = []

    async def wait(delay: float) -> None:
        waits.append(delay)

    monkeypatch.setattr(google_http.asyncio, "sleep", wait)
    client = GoogleWorkbookClient("test-access", "00000000-0000-0000-0000-000000000001")
    endpoint = google_http.SHEETS + "/sheet-id"
    with respx.mock() as router:
        route = router.get(endpoint).respond(200, json={})
        await client.request("GET", endpoint)
        await client.request("GET", endpoint)
        assert waits and 0 < waits[0] <= 1.25
        route.respond(403, json={"error": "private-provider-body"})
        with pytest.raises(GoogleSheetsError, match="Google access was denied") as failure:
            await client.request("GET", endpoint)
        assert "private-provider-body" not in str(failure.value)


@pytest.mark.asyncio
async def test_staged_atomic_workbook_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stable target IDs, inert cells, filters, links and last-good preservation."""
    client = GoogleWorkbookClient("test-access", "00000000-0000-0000-0000-000000000001")
    requests: list[dict[str, object]] = []
    schemas = json.loads(get_static_doc("sheets", "v4"))["schemas"]

    async def provider(method: str, url: str, **kwargs: object) -> dict[str, object]:
        if method == "GET":
            return {
                "sheets": [
                    {
                        "properties": {"sheetId": 7, "title": "Spools"},
                        "developerMetadata": [
                            {
                                "metadataKey": "filament_manager_publication",
                                "metadataValue": client.publication_key,
                            }
                        ],
                    }
                ]
            }
        body = kwargs["json"]
        assert isinstance(body, dict)
        validate_google_request(body, schemas["BatchUpdateSpreadsheetRequest"], schemas)
        requests.extend(body["requests"])
        return {}

    monkeypatch.setattr(client, "request", provider)
    tabs = [
        WorkbookTab(
            "Spools",
            ["id", "spool_code", "filament_product_id", "remaining_mass_effective_g", "archived"],
            [["spool-id", "=1+1", "product-id", 800, False]],
        ),
        WorkbookTab("Filaments", ["id", "name", "material_type"], [["product-id", "PLA Black", "PLA"]]),
    ]
    await client.publish("sheet-id", tabs)
    assert any(item.get("copyPaste", {}).get("destination", {}).get("sheetId") == 7 for item in requests)
    assert any("setBasicFilter" in item for item in requests)
    assert any("addBanding" in item for item in requests)
    assert any("addProtectedRange" in item for item in requests)
    assert any("addChart" in item for item in requests)
    assert '"stringValue": "=1+1"' in json.dumps(requests)
    assert "formulaValue" not in json.dumps(requests)
    assert not any(item.get("deleteSheet", {}).get("sheetId") == 7 for item in requests)
    requests.clear()

    async def failing_provider(method: str, url: str, **kwargs: object) -> dict[str, object]:
        body = kwargs.get("json", {})
        if isinstance(body, dict) and any("updateCells" in item for item in body.get("requests", [])):
            raise GoogleSheetsError("Google publication failed.")
        return await provider(method, url, **kwargs)

    monkeypatch.setattr(client, "request", failing_provider)
    with pytest.raises(GoogleSheetsError):
        await client.publish("sheet-id", tabs)
    assert not any("copyPaste" in item for item in requests)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("guided", [False, True])
async def test_google_oauth_api_and_complete_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, guided: bool
) -> None:
    """Exercise auth/CSRF, encrypted tokens, replay, deletions and coalescing on PG."""
    from filament_manager import main
    from filament_manager.api import dependencies
    from filament_manager.api.routes import google
    from filament_manager.services import events

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        database_url = postgres.get_connection_url()
        settings = integration_settings(database_url, tmp_path)
        settings.app.base_url = "https://testserver"  # type: ignore[assignment]
        settings.google = settings.google.model_copy(
            update={
                "oauth_client_id": "test-client",
                "oauth_client_secret": None,
            }
        )
        from pydantic import SecretStr

        settings.google.oauth_client_secret = SecretStr("test-client-secret")
        settings.google.token_encryption_key = SecretStr(Fernet.generate_key().decode())
        if guided:
            settings.google.oauth_client_id = settings.google.oauth_client_secret = (
                settings.google.token_encryption_key
            ) = None
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
        now = datetime.now(UTC)
        async with factory() as session:
            user = User(
                username="admin",
                normalized_username="admin",
                display_name="Admin",
                password_hash="unused-test-hash",
                role=UserRole.ADMINISTRATOR,
            )
            session.add(user)
            await session.flush()
            session.add(
                UserSession(
                    user_id=user.id,
                    token_hash=hash_token("session-test"),
                    csrf_hash=hash_token("csrf-test"),
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(days=1),
                    idle_expires_at=now + timedelta(days=1),
                )
            )
            product = FilamentProduct(
                material_type="PLA",
                color_name="Black",
                filler="None",
                finish="Standard",
                diameter_mm=Decimal("1.75"),
                density_g_cm3=Decimal("1.24"),
                nominal_net_mass_g=Decimal("1000"),
                archived=True,
            )
            session.add(product)
            await session.commit()
            product_id = product.id

        async def sessions() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

        for module in (main, google, google_connection, google_publication, events):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        app = main.create_app()
        app.dependency_overrides[dependencies.session_dependency] = sessions
        exchanges: list[dict[str, str]] = []

        async def exchange(fields: dict[str, str], record: GoogleConnection | None = None) -> dict[str, str]:
            exchanges.append(fields)
            return {
                "refresh_token": "private-refresh-value",
                "access_token": "test-access",
                "scope": google_connection.DRIVE_SCOPE,
            }

        monkeypatch.setattr(google_connection, "token_request", exchange)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            assert (await client.get("/api/v1/settings/google")).status_code == 401
            client.cookies.set("fm_session", "session-test")
            client.cookies.set("fm_csrf", "csrf-test")
            assert (await client.post("/api/v1/settings/google/connect")).status_code == 403
            client.headers["X-CSRF-Token"] = "csrf-test"
            if guided:
                credentials = {
                    "web": {
                        "client_id": "test-client.apps.googleusercontent.com",
                        "client_secret": "test-guided-secret",
                        "redirect_uris": [google_connection.redirect_uri(settings)],
                    }
                }
                invalid = await client.post(
                    "/api/v1/settings/google/setup",
                    json={"credentials_json": json.dumps({"installed": credentials["web"]})},
                )
                assert invalid.status_code == 422
                saved = await client.post(
                    "/api/v1/settings/google/setup", json={"credentials_json": json.dumps(credentials)}
                )
                assert saved.status_code == 200, saved.text
                assert (tmp_path / "credentials/integration.key").stat().st_mode & 0o077 == 0
                async with factory() as session:
                    record = await session.get(GoogleConnection, 1)
                    assert record and "test-guided-secret" not in record.oauth_client_secret
                    assert google_connection.client_credentials(settings, record) == (
                        credentials["web"]["client_id"],
                        "test-guided-secret",
                    )
                    assert "test-guided-secret" not in str(await snapshot(session))
            started = await client.post("/api/v1/settings/google/connect")
            assert started.status_code == 200, started.text
            query = parse_qs(urlsplit(started.json()["authorization_url"]).query)
            assert query["scope"] == [google_connection.DRIVE_SCOPE]
            assert query["code_challenge_method"] == ["S256"]
            payload = {"state": query["state"][0], "code": "test-code"}
            done = await client.post("/api/v1/settings/google/complete", json=payload)
            assert done.status_code == 200, done.text
            assert done.headers["cache-control"] == "no-store"
            assert (await client.post("/api/v1/settings/google/complete", json=payload)).status_code == 400
            assert len(exchanges) == 1
            status = (await client.get("/api/v1/settings/google")).json()
            assert status["connected"] and status["sync_requested"]
            assert "private-refresh" not in json.dumps(status)
            async with factory() as session:
                record = await session.get(GoogleConnection, 1)
                assert record and record.refresh_token != "private-refresh-value"  # noqa: S105 - test fixture
                assert (
                    google_connection.encryption(settings).decrypt(record.refresh_token.encode()).decode()
                    == "private-refresh-value"
                )
                tables = await snapshot(session)
                filament = next(tab for tab in tables if tab.title == "Filaments")
                assert filament.rows[0][1] == "PLA · Black"
                old_digest = fingerprint(tables)
                with monkeypatch.context() as bounded:
                    bounded.setattr(google_export, "MAX_CONTENT_BYTES", 1)
                    with pytest.raises(GoogleSheetsError, match="safe workbook size"):
                        await snapshot(session)
                await session.delete(await session.get(FilamentProduct, product_id))
                await session.commit()
                assert fingerprint(await snapshot(session)) != old_digest
            published: list[list[WorkbookTab]] = []

            async def create(_self: GoogleWorkbookClient) -> str:
                return "sheet-id"

            async def write(
                _self: GoogleWorkbookClient, _spreadsheet: str, tables: list[WorkbookTab]
            ) -> None:
                published.append(tables)

            monkeypatch.setattr(GoogleWorkbookClient, "find_or_create", create)
            monkeypatch.setattr(GoogleWorkbookClient, "publish", write)
            async with factory() as busy:
                await google_connection.connection(busy, lock=True)
                async with factory() as contender:
                    # A concurrent publisher skips rather than blocking the
                    # worker needed for printer monitoring and physical gates.
                    import asyncio

                    await asyncio.wait_for(google_publication.publish(contender), timeout=1)
                    await contender.rollback()
                await busy.rollback()
            assert published == []
            async with factory() as session:
                await google_publication.publish(session)
                await google_publication.publish(session)
            assert len(published) == 1
            assert (await client.post("/api/v1/settings/google/sync")).status_code == 200
            async with factory() as session:
                await google_publication.publish(session)
            assert len(published) == 2
            assert (await client.post("/api/v1/settings/google/sync")).status_code == 200

            async def unavailable(
                _self: GoogleWorkbookClient, _spreadsheet: str, _tables: list[WorkbookTab]
            ) -> None:
                raise GoogleSheetsError("Google rate limit reached. Publication will retry automatically.")

            monkeypatch.setattr(GoogleWorkbookClient, "publish", unavailable)
            async with factory() as session:
                with pytest.raises(GoogleSheetsError):
                    await google_publication.publish(session)
                failed = await session.get(GoogleConnection, 1)
                assert failed and failed.failures == 1 and failed.next_attempt_at > datetime.now(UTC)
                assert failed.last_fingerprint and failed.sync_requested_at
                # Other granular/periodic jobs share the cooldown rather than flooding Google.
                await google_publication.publish(session)
                assert failed.failures == 1
            monkeypatch.setattr(GoogleWorkbookClient, "publish", write)
            assert (await client.post("/api/v1/settings/google/disconnect")).status_code == 200
            assert (await client.get("/api/v1/settings/google")).json()["connected"] is False
            assert (await client.post("/api/v1/settings/google/sync")).status_code == 409
            async with factory() as session:
                await google_publication.publish(session)
            assert len(published) == 2
        await engine.dispose()
