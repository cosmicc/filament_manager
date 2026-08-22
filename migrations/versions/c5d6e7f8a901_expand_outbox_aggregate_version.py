"""expand outbox aggregate version to bigint

Revision ID: c5d6e7f8a901
Revises: b4c5d6e7f890
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a901"
down_revision: str | None = "b4c5d6e7f890"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow microsecond system-job versions without 32-bit overflow."""

    op.alter_column(
        "outbox_jobs",
        "aggregate_version",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="aggregate_version::bigint",
    )


def downgrade() -> None:
    """Restore the integer column only when every retained value is safe."""

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM outbox_jobs
                WHERE aggregate_version NOT BETWEEN -2147483648 AND 2147483647
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade outbox_jobs.aggregate_version: retained values exceed integer range';
            END IF;
        END
        $$
        """
    )
    op.alter_column(
        "outbox_jobs",
        "aggregate_version",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="aggregate_version::integer",
    )
