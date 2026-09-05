"""Cache template-owned drying guidance on immutable resolved profile snapshots.

Revision ID: e3f4a5b6c789
Revises: d2e3f4a5b678
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op

revision = "e3f4a5b6c789"
down_revision = "d2e3f4a5b678"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Leave old settings unknown; never invent material drying recommendations."""

    op.add_column("material_profiles", sa.Column("drying_temp_c", sa.Numeric(12, 5), nullable=True))


def downgrade() -> None:
    """Remove only the resolved cache; template JSON snapshots remain intact."""

    op.drop_column("material_profiles", "drying_temp_c")
