"""Private singleton Google connection; never included in business publication."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GoogleConnection(Base):
    """Encrypted offline grant and single-use, session-bound OAuth attempt."""

    __tablename__ = "google_connection"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    publication_key: Mapped[str] = mapped_column(String(36), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="oauth", server_default="oauth")
    refresh_token: Mapped[str | None] = mapped_column(Text)
    oauth_client_id: Mapped[str | None] = mapped_column(String(512))
    oauth_client_secret: Mapped[str | None] = mapped_column(Text)
    state_hash: Mapped[str | None] = mapped_column(String(64))
    session_hash: Mapped[str | None] = mapped_column(String(64))
    verifier: Mapped[str | None] = mapped_column(Text)
    state_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    spreadsheet_id: Mapped[str | None] = mapped_column(String(160))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_fingerprint: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(String(300))
    sync_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
