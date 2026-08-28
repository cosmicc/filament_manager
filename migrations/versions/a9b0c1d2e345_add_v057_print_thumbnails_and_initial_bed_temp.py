"""add v0.5.7 print thumbnails and initial bed temperature

Revision ID: a9b0c1d2e345
Revises: f8a9b0c1d234
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e345"
down_revision: str | None = "f8a9b0c1d234"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill layer-zero bed temperatures and add bounded stored print thumbnails."""

    op.add_column(
        "material_profiles",
        sa.Column("initial_bed_temp_c", sa.Numeric(12, 5), nullable=True),
    )
    op.execute("UPDATE material_profiles SET initial_bed_temp_c = bed_temp_c")
    op.alter_column("material_profiles", "initial_bed_temp_c", nullable=False)

    op.add_column("print_jobs", sa.Column("thumbnail_data", sa.LargeBinary(), nullable=True))
    op.add_column("print_jobs", sa.Column("initial_bed_temp_c", sa.Numeric(14, 5), nullable=True))
    op.add_column("print_jobs", sa.Column("thumbnail_media_type", sa.String(32), nullable=True))
    op.add_column("print_jobs", sa.Column("thumbnail_sha256", sa.String(64), nullable=True))
    op.add_column("print_jobs", sa.Column("thumbnail_width", sa.Integer(), nullable=True))
    op.add_column("print_jobs", sa.Column("thumbnail_height", sa.Integer(), nullable=True))
    op.add_column(
        "print_jobs",
        sa.Column("thumbnail_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove stored thumbnails and the separate initial bed-temperature value."""

    op.drop_column("print_jobs", "thumbnail_checked_at")
    op.drop_column("print_jobs", "thumbnail_height")
    op.drop_column("print_jobs", "thumbnail_width")
    op.drop_column("print_jobs", "thumbnail_sha256")
    op.drop_column("print_jobs", "thumbnail_media_type")
    op.drop_column("print_jobs", "thumbnail_data")
    op.drop_column("print_jobs", "initial_bed_temp_c")
    op.drop_column("material_profiles", "initial_bed_temp_c")
