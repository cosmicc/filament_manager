"""Add v0.7.0 immutable print settings snapshot.

Revision ID: b0c1d2e3f456
Revises: a9b0c1d2e345
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b0c1d2e3f456"
down_revision: str | None = "a9b0c1d2e345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a versioned, immutable print-settings evidence document."""

    op.add_column(
        "print_jobs",
        sa.Column(
            "print_settings_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("print_jobs", "print_settings_snapshot", server_default=None)


def downgrade() -> None:
    """Remove the v0.7.0 print-settings evidence document."""

    op.drop_column("print_jobs", "print_settings_snapshot")
