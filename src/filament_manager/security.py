"""Password hashing and random server-side session primitives."""

import hashlib
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import SecurityConfig

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=4)


def normalize_username(username: str) -> str:
    """Normalize local usernames for case-insensitive uniqueness and lookup."""

    normalized = unicodedata.normalize("NFKC", username).strip().casefold()
    if not 2 <= len(normalized) <= 80:
        raise ValueError("username must contain between 2 and 80 characters")
    return normalized


def validate_password(password: str) -> None:
    """Enforce a long-password policy without brittle composition rules."""

    if len(password) < 10:
        raise ValueError("password must contain at least 10 characters")
    if len(password) > 256:
        raise ValueError("password must not exceed 256 characters")


def hash_password(password: str) -> str:
    """Hash a validated password with Argon2id."""

    validate_password(password)
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password without leaking mismatch details."""

    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    """Produce the irreversible database representation of a random token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_pairing_code() -> str:
    """Create a short-lived enrollment secret returned to an administrator once."""

    return f"fm_pair_{secrets.token_urlsafe(32)}"


def create_agent_token() -> str:
    """Create a long-lived, revocable bearer credential returned to an agent once."""

    return f"fm_agent_{secrets.token_urlsafe(48)}"


@dataclass(frozen=True)
class NewSessionTokens:
    """Raw tokens returned once plus their bounded expiration times."""

    session_token: str
    csrf_token: str
    created_at: datetime
    expires_at: datetime
    idle_expires_at: datetime


def create_session_tokens(config: SecurityConfig) -> NewSessionTokens:
    """Create high-entropy session and CSRF tokens."""

    now = datetime.now(UTC)
    return NewSessionTokens(
        session_token=secrets.token_urlsafe(48),
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        expires_at=now + timedelta(hours=config.session_lifetime_hours),
        idle_expires_at=now + timedelta(minutes=config.session_idle_minutes),
    )
