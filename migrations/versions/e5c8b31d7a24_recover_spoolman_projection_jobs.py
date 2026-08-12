"""Recover Spoolman jobs affected by the pre-0.1.5 projection contract.

Revision ID: e5c8b31d7a24
Revises: d4f7a21c9e50
Create Date: 2026-08-11
"""

from alembic import op

revision: str = "e5c8b31d7a24"
down_revision: str | None = "d4f7a21c9e50"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Requeue failed, dead, or abandoned Spoolman work after the contract repair."""

    op.execute(
        """
        UPDATE outbox_jobs
        SET status = 'PENDING'::job_status,
            attempts = 0,
            next_attempt_at = CURRENT_TIMESTAMP,
            locked_by = NULL,
            locked_at = NULL,
            last_error_class = NULL,
            last_error_message = NULL,
            completed_at = NULL
        WHERE job_type LIKE 'spoolman.%'
          AND status IN (
              'RUNNING'::job_status,
              'FAILED'::job_status,
              'DEAD'::job_status
          )
        """
    )


def downgrade() -> None:
    """Keep recovered jobs because their former failure state is not reconstructable."""
