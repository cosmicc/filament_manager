"""Add optional template-owned filament care snapshot fields.

Revision ID: b6c7d8e9f012
Revises: a5b6c7d8e901
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op

revision = "b6c7d8e9f012"
down_revision = "a5b6c7d8e901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Leave historical profiles and template JSON unknown rather than guessing care."""

    op.add_column("material_profiles", sa.Column("drying_time_hours", sa.String(8), nullable=True))
    op.add_column("material_profiles", sa.Column("moisture_sensitivity", sa.String(24), nullable=True))


def downgrade() -> None:
    """Remove the resolved caches without rewriting retained template/print JSON."""

    op.drop_column("material_profiles", "moisture_sensitivity")
    op.drop_column("material_profiles", "drying_time_hours")
