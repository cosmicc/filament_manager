"""Real WebAuthn signatures, PostgreSQL ceremony state, and browser-session contracts."""

import base64
import hashlib
import json
import os
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import cbor2
import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from test_api_integration import integration_settings
from testcontainers.community.postgres import PostgresContainer

from filament_manager import main
from filament_manager.api import dependencies
from filament_manager.api.routes import auth, passkeys
from filament_manager.main import create_app
from filament_manager.models import Base
from filament_manager.models.auth import User
from filament_manager.models.enums import UserRole
from filament_manager.models.passkeys import Passkey, PasskeyChallenge
from filament_manager.security import hash_password
from filament_manager.services import events

PASSWORD = secrets.token_urlsafe(24)


def encoded(data: bytes) -> str:
    """Serialize authenticator bytes with canonical unpadded base64url."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class SoftwareAuthenticator:
    """Independent P-256 authenticator fixture producing real none attestation/assertions."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)

    def registration(
        self, options: dict[str, Any], *, uv: bool = True, origin: str = "http://localhost"
    ) -> dict[str, Any]:
        public = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: public.x.to_bytes(32), -3: public.y.to_bytes(32)})
        flags = 0x41 | (0x04 if uv else 0)
        auth_data = hashlib.sha256(options["rp"]["id"].encode()).digest() + bytes([flags]) + bytes(4)
        auth_data += bytes(16) + len(self.credential_id).to_bytes(2) + self.credential_id + cose
        client = json.dumps(
            {"type": "webauthn.create", "challenge": options["challenge"], "origin": origin}
        ).encode()
        return {
            "id": encoded(self.credential_id),
            "rawId": encoded(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": encoded(client),
                "attestationObject": encoded(
                    cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
                ),
            },
        }

    def assertion(
        self,
        options: dict[str, Any],
        user_id: UUID,
        *,
        counter: int = 1,
        uv: bool = True,
        origin: str = "http://localhost",
        rp_id: str = "localhost",
        challenge: str | None = None,
        corrupt: bool = False,
    ) -> dict[str, Any]:
        """Sign the browser client-data hash and authenticator state independently."""
        client = json.dumps(
            {"type": "webauthn.get", "challenge": challenge or options["challenge"], "origin": origin}
        ).encode()
        auth_data = (
            hashlib.sha256(rp_id.encode()).digest() + bytes([1 | (4 if uv else 0)]) + counter.to_bytes(4)
        )
        signature = self.key.sign(auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        if corrupt:
            signature = signature[:-1] + bytes([signature[-1] ^ 1])
        return {
            "id": encoded(self.credential_id),
            "rawId": encoded(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": encoded(client),
                "authenticatorData": encoded(auth_data),
                "signature": encoded(signature),
                "userHandle": encoded(user_id.bytes),
            },
        }


@pytest_asyncio.fixture
async def passkey_app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[httpx.AsyncClient, Any, UUID]]:
    """Use isolated real PostgreSQL plus the production HTTP dependencies and middleware."""
    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        settings = integration_settings(postgres.get_connection_url())
        settings.app.base_url = "http://localhost"  # type: ignore[assignment]
        settings.app.allowed_hosts = ["localhost"]
        engine = create_async_engine(postgres.get_connection_url())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            user = User(
                username="admin",
                normalized_username="admin",
                display_name="Administrator",
                password_hash=hash_password(PASSWORD),
                role=UserRole.ADMINISTRATOR,
                must_change_password=False,
            )
            session.add(user)
            await session.commit()
            user_id = user.id
        for module in [auth, passkeys, dependencies, events, main]:
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        monkeypatch.setattr(auth, "login_limiter", auth.LoginRateLimiter(attempts=100))
        monkeypatch.setattr(passkeys, "passkey_limiter", auth.LoginRateLimiter(attempts=100))

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        app = create_app()
        app.dependency_overrides[dependencies.session_dependency] = session_override
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            yield client, factory, user_id
        await engine.dispose()


def csrf(client: httpx.AsyncClient) -> dict[str, str]:
    """Use actual strict-cookie CSRF validation for administrative mutations."""
    return {"origin": "http://localhost", "X-CSRF-Token": client.cookies.get("fm_csrf", "")}


async def register(client: httpx.AsyncClient, device: SoftwareAuthenticator) -> UUID:
    """Enroll through the same password-confirmed production endpoints as Settings."""
    response = await client.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200
    response = await client.post(
        "/api/v1/auth/passkeys/register/options",
        headers=csrf(client),
        json={"name": "My phone", "current_password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    options = response.json()
    assert options["authenticatorSelection"]["residentKey"] == "required"
    response = await client.post(
        "/api/v1/auth/passkeys/register/verify",
        headers=csrf(client),
        json={"credential": device.registration(options)},
    )
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"id", "name", "created_at", "last_used_at"}
    return UUID(response.json()["id"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_passkey_login_replay_removal_and_password_fallback(passkey_app: Any) -> None:
    """Prove public-key enrollment and assertions issue real revocable sessions."""
    client, factory, user_id = passkey_app
    device = SoftwareAuthenticator()
    key_id = await register(client, device)
    before = client.cookies.get("fm_session")
    response = await client.get("/api/v1/auth/passkeys")
    assert response.json()[0]["name"] == "My phone"
    response = await client.post("/api/v1/auth/logout", headers=csrf(client))
    assert response.status_code == 204
    response = await client.get("/api/v1/auth/passkeys")
    assert response.status_code == 401
    response = await client.post(
        "/api/v1/auth/passkeys/login/options", headers={"origin": "http://localhost"}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert not response.json().get("allowCredentials")
    assert response.json()["userVerification"] == "required"
    assertion = device.assertion(response.json(), user_id)
    response = await client.post(
        "/api/v1/auth/passkeys/login/verify",
        headers={"origin": "http://localhost"},
        json={"credential": assertion},
    )
    assert response.status_code == 200, response.text
    assert client.cookies.get("fm_session") != before
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    response = await client.post(
        "/api/v1/auth/passkeys/login/verify",
        headers={"origin": "http://localhost"},
        json={"credential": assertion},
    )
    assert response.status_code == 401
    async with factory() as session:
        key = await session.get(Passkey, key_id)
        assert key.sign_count == 1
        assert key.last_used_at is not None
        assert not list(await session.scalars(select(PasskeyChallenge)))
    options = await client.post("/api/v1/auth/passkeys/login/options", headers={"origin": "http://localhost"})
    stale = await client.post(
        "/api/v1/auth/passkeys/login/verify",
        headers={"origin": "http://localhost"},
        json={"credential": device.assertion(options.json(), user_id, counter=1)},
    )
    assert stale.status_code == 401
    response = await client.post(
        f"/api/v1/auth/passkeys/{key_id}/remove", headers=csrf(client), json={"current_password": "wrong"}
    )
    assert response.status_code == 401
    response = await client.post(
        f"/api/v1/auth/passkeys/{key_id}/remove", headers=csrf(client), json={"current_password": PASSWORD}
    )
    assert response.status_code == 204
    assert (await client.get("/api/v1/auth/passkeys")).json() == []
    response = await client.post(
        "/api/v1/auth/passkeys/login/options", headers={"origin": "http://localhost"}
    )
    response = await client.post(
        "/api/v1/auth/passkeys/login/verify",
        headers={"origin": "http://localhost"},
        json={"credential": device.assertion(response.json(), user_id, counter=2)},
    )
    assert response.status_code == 401
    assert (
        await client.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    ).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_passkey_rejects_untrusted_assertions_and_enrollment(passkey_app: Any) -> None:
    """Reject wrong origin, RP, UV, signature, browser cookie, expiry, and CSRF."""
    client, factory, user_id = passkey_app
    device = SoftwareAuthenticator()
    await register(client, device)
    for override in [
        {"origin": "https://evil.example"},
        {"rp_id": "evil.example"},
        {"uv": False},
        {"challenge": encoded(os.urandom(32))},
        {"corrupt": True},
    ]:
        options = await client.post(
            "/api/v1/auth/passkeys/login/options", headers={"origin": "http://localhost"}
        )
        assertion = device.assertion(options.json(), user_id, **override)
        result = await client.post(
            "/api/v1/auth/passkeys/login/verify",
            headers={"origin": "http://localhost"},
            json={"credential": assertion},
        )
        assert result.status_code == 401, result.text
        assert result.json()["message"] == "Passkey could not be verified; try again"
        result = await client.post(
            "/api/v1/auth/passkeys/login/verify",
            headers={"origin": "http://localhost"},
            json={"credential": assertion},
        )
        assert result.json()["code"] == "passkey_challenge_expired"
    options = await client.post("/api/v1/auth/passkeys/login/options", headers={"origin": "http://localhost"})
    async with factory() as session:
        challenge = await session.scalar(select(PasskeyChallenge))
        challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    result = await client.post(
        "/api/v1/auth/passkeys/login/verify",
        headers={"origin": "http://localhost"},
        json={"credential": device.assertion(options.json(), user_id)},
    )
    assert result.json()["code"] == "passkey_challenge_expired"
    options = await client.post("/api/v1/auth/passkeys/login/options", headers={"origin": "http://localhost"})
    assertion = device.assertion(options.json(), user_id)
    result = await client.post(
        "/api/v1/auth/passkeys/login/verify",
        headers={"origin": "http://localhost", "Cookie": ""},
        json={"credential": assertion},
    )
    assert result.json()["code"] == "passkey_challenge_expired"
    assertion["response"]["userHandle"] = encoded(UUID(int=1).bytes)
    result = await client.post(
        "/api/v1/auth/passkeys/login/verify",
        headers={"origin": "http://localhost"},
        json={"credential": assertion},
    )
    assert result.status_code == 401
    assert (
        await client.post("/api/v1/auth/passkeys/login/options", headers={"origin": "https://evil.example"})
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/auth/passkeys/register/options", json={"name": "Key", "current_password": PASSWORD}
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/auth/passkeys/register/options",
            headers=csrf(client),
            json={"name": "Key", "current_password": "wrong"},
        )
    ).status_code == 401
    response = await client.post(
        "/api/v1/auth/passkeys/register/options",
        headers=csrf(client),
        json={"name": "Other", "current_password": PASSWORD},
    )
    response = await client.post(
        "/api/v1/auth/passkeys/register/verify",
        headers=csrf(client),
        json={"credential": SoftwareAuthenticator().registration(response.json(), uv=False)},
    )
    assert response.status_code == 401

    for condition in ("disabled", "locked"):
        async with factory() as session:
            user = await session.get(User, user_id)
            user.is_active = condition != "disabled"
            user.locked_until = datetime.now(UTC) + timedelta(minutes=5) if condition == "locked" else None
            await session.commit()
        options = await client.post(
            "/api/v1/auth/passkeys/login/options", headers={"origin": "http://localhost"}
        )
        result = await client.post(
            "/api/v1/auth/passkeys/login/verify",
            headers={"origin": "http://localhost"},
            json={"credential": device.assertion(options.json(), user_id)},
        )
        assert result.status_code == 401
    async with factory() as session:
        user = await session.get(User, user_id)
        user.is_active = True
        user.locked_until = None
        user.must_change_password = True
        await session.commit()
    options = await client.post("/api/v1/auth/passkeys/login/options", headers={"origin": "http://localhost"})
    result = await client.post(
        "/api/v1/auth/passkeys/login/verify",
        headers={"origin": "http://localhost"},
        json={"credential": device.assertion(options.json(), user_id)},
    )
    assert result.status_code == 200
    assert result.json()["user"]["must_change_password"] is True
    assert (await client.get("/api/v1/auth/passkeys")).status_code == 403


@pytest.mark.integration
def test_passkey_migration_preserves_account_and_refuses_credential_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Upgrade populated 0.9.2 data, check metadata parity, and refuse unsafe downgrade."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import Session

    from filament_manager.config import get_settings

    with PostgresContainer("postgres:17-alpine", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        monkeypatch.setenv("FILAMENT_MANAGER_DATABASE_URL", url)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        engine = create_engine(url)
        try:
            command.upgrade(config, "fd345e6f7890")
            with Session(engine) as session:
                user = User(
                    username="admin",
                    normalized_username="admin",
                    display_name="Administrator",
                    password_hash=hash_password(PASSWORD),
                    role=UserRole.ADMINISTRATOR,
                )
                session.add(user)
                session.commit()
                user_id, password_hash = user.id, user.password_hash
            command.upgrade(config, "head")
            command.check(config)
            assert {"passkeys", "passkey_challenges"} <= set(inspect(engine).get_table_names())
            with Session(engine) as session:
                assert session.get(User, user_id).password_hash == password_hash
                session.add(
                    Passkey(
                        user_id=user_id,
                        name="Saved credential",
                        rp_id="localhost",
                        credential_id=os.urandom(32),
                        public_key=os.urandom(64),
                        sign_count=0,
                        backed_up=False,
                        device_type="single_device",
                        transports=[],
                    )
                )
                session.commit()
            with pytest.raises(RuntimeError, match="Passkeys exist"):
                command.downgrade(config, "fd345e6f7890")
            with Session(engine) as session:
                assert session.scalar(select(Passkey)) is not None
                session.delete(session.scalar(select(Passkey)))
                session.commit()
            command.downgrade(config, "fd345e6f7890")
            assert "passkeys" not in inspect(engine).get_table_names()
        finally:
            engine.dispose()
            get_settings.cache_clear()
