"""Public passkey credentials and short-lived browser-bound WebAuthn ceremonies."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Passkey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One discoverable credential; private keys never leave the authenticator."""

    __tablename__ = "passkeys"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    rp_id: Mapped[str] = mapped_column(String(253))
    credential_id: Mapped[bytes] = mapped_column(LargeBinary(1024), unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary(4096))
    sign_count: Mapped[int] = mapped_column(BigInteger)
    backed_up: Mapped[bool] = mapped_column(Boolean)
    device_type: Mapped[str] = mapped_column(String(32))
    transports: Mapped[list[str]] = mapped_column(JSONB, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasskeyChallenge(UUIDPrimaryKeyMixin, Base):
    """A single-use challenge bound to an HttpOnly browser cookie and purpose."""

    __tablename__ = "passkey_challenges"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(16))
    challenge: Mapped[bytes] = mapped_column(LargeBinary(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_hash: Mapped[str | None] = mapped_column(String(64))
    user_version: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(80))
