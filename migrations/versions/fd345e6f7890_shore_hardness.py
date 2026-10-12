"""Cache optional, atomic inherited Shore hardness without guessing old values.

Revision ID: fd345e6f7890
Revises: fc234d5e6f78
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "fd345e6f7890"
down_revision = "fc234d5e6f78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Leave existing resolved caches and immutable template/history JSON untouched."""
    op.add_column("material_profiles", sa.Column("shore_hardness", JSONB(none_as_null=True), nullable=True))


def downgrade() -> None:
    """Require a backup rather than silently discarding entered hardness."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM material_profiles WHERE shore_hardness IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM material_template_revisions "
            "WHERE settings->'shore_hardness' IS NOT NULL "
            "AND settings->'shore_hardness' <> 'null'::jsonb)"
        )
    ):
        raise RuntimeError("Shore hardness exists; restore a pre-upgrade backup to downgrade")
    op.drop_column("material_profiles", "shore_hardness")
