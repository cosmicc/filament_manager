"""add Cura workstation agents and deployments

Revision ID: 2f6e9d8c4b31
Revises: 809125e61af1
Create Date: 2026-08-05 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2f6e9d8c4b31"
down_revision: str | None = "809125e61af1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create revocable agent enrollment and leased deployment state."""

    deployment_status = postgresql.ENUM(
        "PENDING",
        "CLAIMED",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        name="cura_deployment_status",
        create_type=False,
    )
    deployment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "workstation_agents",
        sa.Column("agent_code", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("architecture", sa.String(length=64), nullable=False),
        sa.Column("agent_version", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cura_installations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_workstation_agents_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workstation_agents")),
        sa.UniqueConstraint("agent_code", name=op.f("uq_workstation_agents_agent_code")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_workstation_agents_token_hash")),
    )
    op.create_index(
        op.f("ix_workstation_agents_last_seen_at"), "workstation_agents", ["last_seen_at"], unique=False
    )

    op.create_table(
        "workstation_pairing_codes",
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_agent_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["consumed_by_agent_id"],
            ["workstation_agents.id"],
            name=op.f("fk_workstation_pairing_codes_consumed_by_agent_id_workstation_agents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_workstation_pairing_codes_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workstation_pairing_codes")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_workstation_pairing_codes_code_hash")),
    )
    op.create_index(
        op.f("ix_workstation_pairing_codes_expires_at"),
        "workstation_pairing_codes",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "cura_deployments",
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("material_profile_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("status", deployment_status, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_checksum", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=192), nullable=False),
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
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["workstation_agents.id"],
            name=op.f("fk_cura_deployments_agent_id_workstation_agents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["material_profile_id"],
            ["material_profiles.id"],
            name=op.f("fk_cura_deployments_material_profile_id_material_profiles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_cura_deployments_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cura_deployments")),
        sa.UniqueConstraint("idempotency_key", name="uq_cura_deployment_idempotency"),
    )
    op.create_index(op.f("ix_cura_deployments_agent_id"), "cura_deployments", ["agent_id"], unique=False)
    op.create_index(
        "ix_cura_deployment_claim",
        "cura_deployments",
        ["agent_id", "status", "next_attempt_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove workstation deployment state without touching material profiles."""

    op.drop_index("ix_cura_deployment_claim", table_name="cura_deployments")
    op.drop_index(op.f("ix_cura_deployments_agent_id"), table_name="cura_deployments")
    op.drop_table("cura_deployments")
    op.drop_index(op.f("ix_workstation_pairing_codes_expires_at"), table_name="workstation_pairing_codes")
    op.drop_table("workstation_pairing_codes")
    op.drop_index(op.f("ix_workstation_agents_last_seen_at"), table_name="workstation_agents")
    op.drop_table("workstation_agents")
    postgresql.ENUM(name="cura_deployment_status").drop(op.get_bind(), checkfirst=True)
