"""add filament product archival and display palettes

Revision ID: e1f2a3b4c567
Revises: d0e1f2a3b456
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f2a3b4c567"
down_revision: str | None = "d0e1f2a3b456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add reversible product archival and richer display palettes."""

    op.add_column(
        "filament_products",
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(
        "ix_filament_products_archived",
        "filament_products",
        ["archived"],
    )
    for table_name in ("filament_colors", "filament_products"):
        op.add_column(
            table_name,
            sa.Column(
                "color_mode",
                sa.String(length=16),
                server_default=sa.text("'solid'"),
                nullable=False,
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "color_hexes",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )
        op.execute(
            sa.text(
                f"UPDATE {table_name} SET color_hexes = "
                "CASE WHEN color_hex IS NULL THEN '[]'::jsonb "
                "ELSE jsonb_build_array(color_hex) END"
            )
        )


def downgrade() -> None:
    """Remove product archival and display palettes."""

    for table_name in ("filament_products", "filament_colors"):
        op.drop_column(table_name, "color_hexes")
        op.drop_column(table_name, "color_mode")
    op.drop_index("ix_filament_products_archived", table_name="filament_products")
    op.drop_column("filament_products", "archived")
