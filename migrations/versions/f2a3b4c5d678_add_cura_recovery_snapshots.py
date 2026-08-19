"""add sanitized Cura recovery snapshots and restore requests

Revision ID: f2a3b4c5d678
Revises: e1f2a3b4c567
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d678"
down_revision: str | None = "e1f2a3b4c567"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store ten bounded recovery points and their leased restore work."""

    deployment_status = postgresql.ENUM(
        "PENDING",
        "CLAIMED",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        name="cura_deployment_status",
        create_type=False,
    )
    op.add_column(
        "workstation_agents",
        sa.Column(
            "cura_recovery_status",
            sa.String(length=32),
            server_default=sa.text("'not_ready'"),
            nullable=False,
        ),
    )
    op.add_column(
        "workstation_agents",
        sa.Column("cura_recovery_message", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "workstation_agents",
        sa.Column("last_recovery_snapshot_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workstation_agents",
        sa.Column("last_recovery_restore_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "cura_recovery_snapshots",
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("installation_id", sa.String(length=96), nullable=False),
        sa.Column("cura_version", sa.String(length=32), nullable=False),
        sa.Column("setting_version", sa.Integer(), nullable=True),
        sa.Column("snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("machine_count", sa.Integer(), nullable=False),
        sa.Column("quality_profile_count", sa.Integer(), nullable=False),
        sa.Column("plugin_count", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["workstation_agents.id"],
            name=op.f("fk_cura_recovery_snapshots_agent_id_workstation_agents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cura_recovery_snapshots")),
        sa.UniqueConstraint(
            "agent_id",
            "installation_id",
            "cura_version",
            "snapshot_checksum",
            name="uq_cura_recovery_snapshot_content",
        ),
    )
    op.create_index(
        op.f("ix_cura_recovery_snapshots_agent_id"),
        "cura_recovery_snapshots",
        ["agent_id"],
    )
    op.create_index(
        "ix_cura_recovery_snapshot_history",
        "cura_recovery_snapshots",
        ["agent_id", "installation_id", "cura_version", "captured_at"],
    )

    op.create_table(
        "cura_recovery_restores",
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=True),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("installation_id", sa.String(length=96), nullable=False),
        sa.Column("cura_version", sa.String(length=32), nullable=False),
        sa.Column("snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", deployment_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_error_class", sa.String(length=160), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["workstation_agents.id"],
            name=op.f("fk_cura_recovery_restores_agent_id_workstation_agents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["cura_recovery_snapshots.id"],
            name=op.f("fk_cura_recovery_restores_snapshot_id_cura_recovery_snapshots"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_cura_recovery_restores_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cura_recovery_restores")),
    )
    op.create_index(
        op.f("ix_cura_recovery_restores_agent_id"),
        "cura_recovery_restores",
        ["agent_id"],
    )
    op.create_index(
        op.f("ix_cura_recovery_restores_snapshot_id"),
        "cura_recovery_restores",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_cura_recovery_restore_claim",
        "cura_recovery_restores",
        ["agent_id", "status", "next_attempt_at", "created_at"],
    )


def downgrade() -> None:
    """Remove Cura recovery history and restore work."""

    op.drop_index("ix_cura_recovery_restore_claim", table_name="cura_recovery_restores")
    op.drop_index(
        op.f("ix_cura_recovery_restores_snapshot_id"),
        table_name="cura_recovery_restores",
    )
    op.drop_index(
        op.f("ix_cura_recovery_restores_agent_id"),
        table_name="cura_recovery_restores",
    )
    op.drop_table("cura_recovery_restores")
    op.drop_index("ix_cura_recovery_snapshot_history", table_name="cura_recovery_snapshots")
    op.drop_index(
        op.f("ix_cura_recovery_snapshots_agent_id"),
        table_name="cura_recovery_snapshots",
    )
    op.drop_table("cura_recovery_snapshots")
    op.drop_column("workstation_agents", "last_recovery_restore_at")
    op.drop_column("workstation_agents", "last_recovery_snapshot_at")
    op.drop_column("workstation_agents", "cura_recovery_message")
    op.drop_column("workstation_agents", "cura_recovery_status")
