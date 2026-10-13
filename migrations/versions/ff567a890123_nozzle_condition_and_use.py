"""Add build-plate condition and availability choices to physical nozzles."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ff567a890123"
down_revision = "fe456f789012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve installation and retirement while adding conservative defaults."""
    op.add_column(
        "nozzles",
        sa.Column(
            "condition",
            postgresql.ENUM(name="plate_condition", create_type=False),
            nullable=False,
            server_default="GOOD",
        ),
    )
    op.add_column(
        "nozzles",
        sa.Column(
            "usage_status",
            postgresql.ENUM(name="plate_status", create_type=False),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.execute("UPDATE nozzles SET usage_status = 'RETIRED' WHERE status = 'RETIRED'")
    op.alter_column("nozzles", "condition", server_default=None)
    op.alter_column("nozzles", "usage_status", server_default=None)


def downgrade() -> None:
    """Refuse to silently discard entered condition or maintenance information."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM nozzles WHERE condition <> 'GOOD' OR usage_status = 'MAINTENANCE')"
        )
    ):
        raise RuntimeError("Nozzle condition or maintenance data exists; restore a pre-upgrade backup")
    op.drop_column("nozzles", "usage_status")
    op.drop_column("nozzles", "condition")
