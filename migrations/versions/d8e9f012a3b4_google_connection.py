"""Add private encrypted Google connection state.

Revision ID: d8e9f012a3b4
Revises: c7d8e9f012a3
"""

import sqlalchemy as sa
from alembic import op

revision = "d8e9f012a3b4"
down_revision = "c7d8e9f012a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add an empty, opt-in connection without changing inventory."""
    op.create_table(
        "google_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("publication_key", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="oauth"),
        sa.Column("refresh_token", sa.Text()),
        sa.Column("state_hash", sa.String(64)),
        sa.Column("session_hash", sa.String(64)),
        sa.Column("verifier", sa.Text()),
        sa.Column("state_expires_at", sa.DateTime(timezone=True)),
        sa.Column("spreadsheet_id", sa.String(160)),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_fingerprint", sa.String(64)),
        sa.Column("last_error", sa.String(300)),
        sa.Column("sync_requested_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("id = 1", name=op.f("ck_google_connection_singleton")),
    )


def downgrade() -> None:
    """Remove the connection; the published workbook remains in Drive."""
    op.drop_table("google_connection")
