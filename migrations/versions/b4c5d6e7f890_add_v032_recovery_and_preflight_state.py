"""add v0.3.2 recovery metadata and spool preflight state

Revision ID: b4c5d6e7f890
Revises: a3b4c5d6e789
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4c5d6e7f890"
down_revision: str | None = "a3b4c5d6e789"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add named/manual recovery points and durable preflight health state."""

    op.add_column(
        "workstation_agents",
        sa.Column(
            "suppressed_recovery_snapshots",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_constraint("uq_cura_recovery_snapshot_content", "cura_recovery_snapshots", type_="unique")
    op.add_column("cura_recovery_snapshots", sa.Column("capture_request_id", sa.Uuid(), nullable=True))
    op.add_column("cura_recovery_snapshots", sa.Column("created_by", sa.Uuid(), nullable=True))
    op.add_column(
        "cura_recovery_snapshots",
        sa.Column("capture_kind", sa.String(length=16), server_default="automatic", nullable=False),
    )
    op.add_column("cura_recovery_snapshots", sa.Column("name", sa.String(length=120), nullable=True))
    op.add_column("cura_recovery_snapshots", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "cura_recovery_snapshots",
        sa.Column("record_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_foreign_key(
        "fk_cura_recovery_snapshots_capture_request",
        "cura_recovery_snapshots",
        "cura_deployments",
        ["capture_request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_cura_recovery_snapshots_created_by",
        "cura_recovery_snapshots",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_cura_recovery_snapshot_capture_request",
        "cura_recovery_snapshots",
        ["capture_request_id"],
    )
    op.create_index(
        "uq_cura_recovery_snapshot_automatic_content",
        "cura_recovery_snapshots",
        ["agent_id", "installation_id", "cura_version", "snapshot_checksum"],
        unique=True,
        postgresql_where=sa.text("capture_request_id IS NULL"),
    )

    op.add_column(
        "printers",
        sa.Column("spool_preflight_status", sa.String(length=32), server_default="unknown", nullable=False),
    )
    op.add_column("printers", sa.Column("spool_preflight_message", sa.String(length=500), nullable=True))
    op.add_column(
        "printers",
        sa.Column("last_spool_preflight_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbox_jobs",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE outbox_jobs SET last_error_at = COALESCE(locked_at, created_at) "
        "WHERE last_error_class IS NOT NULL"
    )

    # The pre-v0.3.2 scheduler retained every terminal periodic run as
    # actionable until a later success. Preserve that history while removing
    # the accumulated queue debt; the scheduler immediately creates a fresh
    # bounded attempt for each configured recurring service.
    op.execute(
        "UPDATE outbox_jobs "
        "SET status = 'SUPERSEDED'::job_status, "
        "completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) "
        "WHERE status IN ('FAILED'::job_status, 'DEAD'::job_status) "
        "AND idempotency_key LIKE 'periodic:%'"
    )
    # A new full Spoolman pass reconstructs current metadata, so stale granular
    # upserts do not need to be replayed individually. Deletes, explicit weight
    # adjustments, and any other non-reconstructable work are requeued instead.
    op.execute(
        "UPDATE outbox_jobs "
        "SET status = 'SUPERSEDED'::job_status, "
        "completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) "
        "WHERE status IN ('FAILED'::job_status, 'DEAD'::job_status) "
        "AND job_type IN ("
        "'spoolman.vendor.upsert', "
        "'spoolman.filament.upsert', "
        "'spoolman.spool.upsert'"
        ")"
    )
    op.execute(
        "UPDATE outbox_jobs "
        "SET status = 'PENDING'::job_status, attempts = 0, "
        "next_attempt_at = CURRENT_TIMESTAMP, locked_by = NULL, locked_at = NULL, "
        "completed_at = NULL "
        "WHERE status IN ('FAILED'::job_status, 'DEAD'::job_status) "
        "AND job_type LIKE 'spoolman.%'"
    )


def downgrade() -> None:
    """Remove v0.3.2 recovery metadata and preflight health state."""

    op.drop_column("outbox_jobs", "last_error_at")
    op.drop_column("printers", "last_spool_preflight_sync_at")
    op.drop_column("printers", "spool_preflight_message")
    op.drop_column("printers", "spool_preflight_status")
    op.drop_index("uq_cura_recovery_snapshot_automatic_content", table_name="cura_recovery_snapshots")
    op.drop_constraint("uq_cura_recovery_snapshot_capture_request", "cura_recovery_snapshots", type_="unique")
    op.drop_constraint("fk_cura_recovery_snapshots_created_by", "cura_recovery_snapshots", type_="foreignkey")
    op.drop_constraint(
        "fk_cura_recovery_snapshots_capture_request", "cura_recovery_snapshots", type_="foreignkey"
    )
    op.drop_column("cura_recovery_snapshots", "record_version")
    op.drop_column("cura_recovery_snapshots", "description")
    op.drop_column("cura_recovery_snapshots", "name")
    op.drop_column("cura_recovery_snapshots", "capture_kind")
    op.drop_column("cura_recovery_snapshots", "created_by")
    op.drop_column("cura_recovery_snapshots", "capture_request_id")
    op.create_unique_constraint(
        "uq_cura_recovery_snapshot_content",
        "cura_recovery_snapshots",
        ["agent_id", "installation_id", "cura_version", "snapshot_checksum"],
    )
    op.drop_column("workstation_agents", "suppressed_recovery_snapshots")
