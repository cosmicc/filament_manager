"""add physical nozzles and recovery diagnostics

Revision ID: c9d0e1f2a345
Revises: b8c9d0e1f234
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a345"
down_revision: str | None = "b8c9d0e1f234"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create physical nozzle history and persisted validation results."""

    nozzle_status = postgresql.ENUM(
        "AVAILABLE", "INSTALLED", "RETIRED", name="nozzle_status", create_type=False
    )
    nozzle_status.create(op.get_bind(), checkfirst=True)

    op.add_column("material_profiles", sa.Column("source_workstation_agent_id", sa.UUID(), nullable=True))
    op.add_column(
        "material_profiles", sa.Column("source_cura_material_id", sa.String(length=64), nullable=True)
    )
    op.create_foreign_key(
        "fk_material_profiles_cura_source_agent",
        "material_profiles",
        "workstation_agents",
        ["source_workstation_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_material_profiles_source_workstation_agent_id"),
        "material_profiles",
        ["source_workstation_agent_id"],
    )
    op.create_unique_constraint(
        "uq_material_profiles_cura_source",
        "material_profiles",
        ["source_workstation_agent_id", "source_cura_material_id"],
    )

    op.create_table(
        "nozzles",
        sa.Column("nozzle_code", sa.String(length=64), nullable=False),
        sa.Column("diameter_mm", sa.Numeric(12, 5), nullable=False),
        sa.Column("material", sa.String(length=96), nullable=False),
        sa.Column("manufacturer", sa.String(length=160), nullable=True),
        sa.Column("product_name", sa.String(length=160), nullable=True),
        sa.Column("coating", sa.String(length=96), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("status", nozzle_status, nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("diameter_mm > 0", name="nozzle_diameter_positive"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nozzles")),
        sa.UniqueConstraint("nozzle_code", name=op.f("uq_nozzles_nozzle_code")),
    )
    op.create_index("ix_nozzles_status_code", "nozzles", ["status", "nozzle_code"])

    op.add_column("printers", sa.Column("active_nozzle_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_printers_active_nozzle_id_nozzles"),
        "printers",
        "nozzles",
        ["active_nozzle_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(op.f("uq_printers_active_nozzle_id"), "printers", ["active_nozzle_id"])

    op.add_column("print_jobs", sa.Column("nozzle_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_print_jobs_nozzle_id_nozzles"),
        "print_jobs",
        "nozzles",
        ["nozzle_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_print_jobs_nozzle_id"), "print_jobs", ["nozzle_id"])

    op.create_table(
        "nozzle_lifecycle_events",
        sa.Column("nozzle_id", sa.UUID(), nullable=False),
        sa.Column("printer_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("performed_by", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('installed', 'removed', 'retired', 'reactivated')",
            name="event_type",
        ),
        sa.ForeignKeyConstraint(
            ["nozzle_id"],
            ["nozzles.id"],
            name=op.f("fk_nozzle_lifecycle_events_nozzle_id_nozzles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["printer_id"],
            ["printers.id"],
            name=op.f("fk_nozzle_lifecycle_events_printer_id_printers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"],
            ["users.id"],
            name=op.f("fk_nozzle_lifecycle_events_performed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nozzle_lifecycle_events")),
    )
    op.create_index("ix_nozzle_lifecycle_time", "nozzle_lifecycle_events", ["nozzle_id", "occurred_at"])

    op.create_table(
        "diagnostic_runs",
        sa.Column("run_type", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_diagnostic_runs_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnostic_runs")),
    )
    op.create_index("ix_diagnostic_runs_started", "diagnostic_runs", ["started_at"])

    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=160), nullable=False),
        sa.Column("worker_type", sa.String(length=32), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_job_id", sa.UUID(), nullable=True),
        sa.Column("current_job_type", sa.String(length=96), nullable=True),
        sa.Column("last_error_class", sa.String(length=160), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_heartbeats")),
        sa.UniqueConstraint("worker_id", name=op.f("uq_worker_heartbeats_worker_id")),
    )
    op.create_index("ix_worker_heartbeats_seen", "worker_heartbeats", ["last_seen_at"])


def downgrade() -> None:
    """Remove v0.2.2 nozzle and diagnostics structures."""

    op.drop_index("ix_worker_heartbeats_seen", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
    op.drop_index("ix_diagnostic_runs_started", table_name="diagnostic_runs")
    op.drop_table("diagnostic_runs")
    op.drop_index("ix_nozzle_lifecycle_time", table_name="nozzle_lifecycle_events")
    op.drop_table("nozzle_lifecycle_events")
    op.drop_index(op.f("ix_print_jobs_nozzle_id"), table_name="print_jobs")
    op.drop_constraint(op.f("fk_print_jobs_nozzle_id_nozzles"), "print_jobs", type_="foreignkey")
    op.drop_column("print_jobs", "nozzle_id")
    op.drop_constraint(op.f("uq_printers_active_nozzle_id"), "printers", type_="unique")
    op.drop_constraint(op.f("fk_printers_active_nozzle_id_nozzles"), "printers", type_="foreignkey")
    op.drop_column("printers", "active_nozzle_id")
    op.drop_index("ix_nozzles_status_code", table_name="nozzles")
    op.drop_table("nozzles")
    postgresql.ENUM(name="nozzle_status").drop(op.get_bind(), checkfirst=True)
    op.drop_constraint("uq_material_profiles_cura_source", "material_profiles", type_="unique")
    op.drop_index(
        op.f("ix_material_profiles_source_workstation_agent_id"),
        table_name="material_profiles",
    )
    op.drop_constraint("fk_material_profiles_cura_source_agent", "material_profiles", type_="foreignkey")
    op.drop_column("material_profiles", "source_cura_material_id")
    op.drop_column("material_profiles", "source_workstation_agent_id")
