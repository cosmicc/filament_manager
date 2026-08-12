"""add one-time Spoolman location adoption state

Revision ID: c7e4a19d2b63
Revises: b91d2e4f7a10
Create Date: 2026-08-11 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e4a19d2b63"
down_revision: str | None = "b91d2e4f7a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Mark existing canonical locations owned and leave empty rows importable."""

    op.add_column(
        "spools",
        sa.Column(
            "location_authoritative",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.execute(sa.text("UPDATE spools SET location_authoritative = TRUE WHERE location IS NOT NULL"))
    op.alter_column(
        "spools",
        "location_authoritative",
        existing_type=sa.Boolean(),
        server_default=sa.true(),
    )


def downgrade() -> None:
    """Remove the internal ownership marker without changing locations."""

    op.drop_column("spools", "location_authoritative")
