"""Remember location choices without changing canonical spool assignments.

Revision ID: d2e3f4a5b678
Revises: c1d2e3f4a567
Create Date: 2026-09-05
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d2e3f4a5b678"
down_revision = "c1d2e3f4a567"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Seed exact distinct labels, including archived spools, without merging groups."""

    choices = op.create_table(
        "spool_location_choices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    connection = op.get_bind()
    names = connection.execute(sa.text("SELECT DISTINCT location FROM spools WHERE location IS NOT NULL"))
    for (name,) in names:
        if name.strip():
            connection.execute(choices.insert().values(id=uuid4(), name=name))


def downgrade() -> None:
    """Drop only remembered choices; all spool locations remain intact."""

    op.drop_table("spool_location_choices")
