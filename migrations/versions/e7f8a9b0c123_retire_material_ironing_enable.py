"""retire material-scoped ironing enablement

Revision ID: e7f8a9b0c123
Revises: d6e7f8a9b012
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c123"
down_revision: str | None = "d6e7f8a9b012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove the obsolete material value now owned by Cura quality profiles."""

    op.drop_column("material_profiles", "ironing_enabled")


def downgrade() -> None:
    """Restore the former nullable material flag without reconstructing retired values."""

    op.add_column("material_profiles", sa.Column("ironing_enabled", sa.Boolean(), nullable=True))
