"""add material templates and authoritative Cura library state

Revision ID: b91d2e4f7a10
Revises: 8c3a0f1e7d92
Create Date: 2026-08-11 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b91d2e4f7a10"
down_revision: str | None = "8c3a0f1e7d92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create versioned templates and opt-in full Cura-library management."""

    profile_status = postgresql.ENUM(
        "DRAFT",
        "CALIBRATION_IN_PROGRESS",
        "VALIDATED",
        "PUBLISHED",
        "SUPERSEDED",
        "ARCHIVED",
        name="profile_status",
        create_type=False,
    )
    op.create_table(
        "material_templates",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("material_type", sa.String(length=48), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("printer_id", sa.UUID(), nullable=False),
        sa.Column("nozzle_diameter_mm", sa.Numeric(precision=12, scale=5), nullable=False),
        sa.Column("filament_diameter_mm", sa.Numeric(precision=12, scale=5), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["printer_id"],
            ["printers.id"],
            name=op.f("fk_material_templates_printer_id_printers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_templates")),
        sa.UniqueConstraint(
            "material_type",
            "printer_id",
            "nozzle_diameter_mm",
            name="uq_material_template_scope",
        ),
    )
    op.create_index(
        op.f("ix_material_templates_material_type"),
        "material_templates",
        ["material_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_material_templates_printer_id"),
        "material_templates",
        ["printer_id"],
        unique=False,
    )
    op.create_table(
        "material_template_revisions",
        sa.Column("material_template_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", profile_status, nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["material_template_id"],
            ["material_templates.id"],
            name=op.f("fk_material_template_revisions_material_template_id_material_templates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_template_revisions")),
        sa.UniqueConstraint(
            "material_template_id",
            "version",
            name="uq_material_template_revision_version",
        ),
    )
    op.create_index(
        op.f("ix_material_template_revisions_material_template_id"),
        "material_template_revisions",
        ["material_template_id"],
        unique=False,
    )

    for table_name in ("filament_products", "material_profiles"):
        op.add_column(
            table_name,
            sa.Column("source_template_revision_id", sa.UUID(), nullable=True),
        )
        op.create_foreign_key(
            op.f(f"fk_{table_name}_source_template_revision_id_material_template_revisions"),
            table_name,
            "material_template_revisions",
            ["source_template_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            op.f(f"ix_{table_name}_source_template_revision_id"),
            table_name,
            ["source_template_revision_id"],
            unique=False,
        )

    op.add_column(
        "workstation_agents",
        sa.Column(
            "cura_management_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.alter_column("workstation_agents", "cura_management_enabled", server_default=None)
    op.alter_column(
        "cura_deployments",
        "material_profile_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.alter_column(
        "cura_deployments",
        "requested_by",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    """Remove templates after refusing to discard template-derived product history."""

    connection = op.get_bind()
    referenced = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
              SELECT 1 FROM filament_products WHERE source_template_revision_id IS NOT NULL
              UNION ALL
              SELECT 1 FROM material_profiles WHERE source_template_revision_id IS NOT NULL
            )
            """
        )
    ).scalar_one()
    if referenced:
        raise RuntimeError(
            "Cannot downgrade while filament products or profiles reference material templates"
        )

    op.alter_column("cura_deployments", "requested_by", existing_type=sa.UUID(), nullable=False)
    op.alter_column("cura_deployments", "material_profile_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("workstation_agents", "cura_management_enabled")
    for table_name in ("material_profiles", "filament_products"):
        op.drop_index(op.f(f"ix_{table_name}_source_template_revision_id"), table_name=table_name)
        op.drop_constraint(
            op.f(f"fk_{table_name}_source_template_revision_id_material_template_revisions"),
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "source_template_revision_id")
    op.drop_index(
        op.f("ix_material_template_revisions_material_template_id"),
        table_name="material_template_revisions",
    )
    op.drop_table("material_template_revisions")
    op.drop_index(op.f("ix_material_templates_printer_id"), table_name="material_templates")
    op.drop_index(op.f("ix_material_templates_material_type"), table_name="material_templates")
    op.drop_table("material_templates")
