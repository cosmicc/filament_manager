"""Add public passkeys and browser-bound single-use ceremonies.

Revision ID: fe456f789012
Revises: fd345e6f7890
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "fe456f789012"
down_revision = "fd345e6f7890"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve passwords and sessions while adding optional credentials."""

    op.create_table(
        "passkeys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("rp_id", sa.String(253), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(1024), nullable=False, unique=True),
        sa.Column("public_key", sa.LargeBinary(4096), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("backed_up", sa.Boolean(), nullable=False),
        sa.Column("device_type", sa.String(32), nullable=False),
        sa.Column("transports", JSONB(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_passkeys_user_id", "passkeys", ["user_id"])
    op.create_table(
        "passkey_challenges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("challenge", sa.LargeBinary(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("session_hash", sa.String(64), nullable=True),
        sa.Column("user_version", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(80), nullable=True),
    )
    op.create_index("ix_passkey_challenges_expires_at", "passkey_challenges", ["expires_at"])


def downgrade() -> None:
    """Refuse to silently discard registered authenticators."""

    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM passkeys)")):
        raise RuntimeError("Passkeys exist; remove them in Settings or restore a pre-upgrade backup")
    op.drop_table("passkey_challenges")
    op.drop_table("passkeys")
