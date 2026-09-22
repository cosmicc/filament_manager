"""Retain bounded exact G-code independently of print list queries.

Revision ID: fc234d5e6f78
Revises: fb123c4d5e67
"""

import sqlalchemy as sa
from alembic import op

revision = "fc234d5e6f78"
down_revision = "fb123c4d5e67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep originals out of JSON publication and ordinary history loads."""
    op.create_table(
        "print_gcode_archives",
        sa.Column(
            "print_job_id", sa.Uuid(), sa.ForeignKey("print_jobs.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("compressed_data", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    """Refuse to silently discard retained print inputs."""
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM print_gcode_archives)")):
        raise RuntimeError("Saved G-code exists; restore a pre-upgrade backup to downgrade")
    op.drop_table("print_gcode_archives")
