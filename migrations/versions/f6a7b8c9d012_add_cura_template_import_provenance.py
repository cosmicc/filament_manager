"""add Cura template import provenance

Revision ID: f6a7b8c9d012
Revises: e5c8b31d7a24
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d012"
down_revision: str | None = "e5c8b31d7a24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Track draft templates imported from one reported Cura material."""

    op.add_column(
        "material_templates",
        sa.Column("source_workstation_agent_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "material_templates",
        sa.Column("source_cura_material_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_material_templates_cura_source_agent",
        "material_templates",
        "workstation_agents",
        ["source_workstation_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_material_templates_source_workstation_agent_id"),
        "material_templates",
        ["source_workstation_agent_id"],
        unique=False,
    )
    op.drop_constraint(
        "uq_material_template_scope",
        "material_templates",
        type_="unique",
    )
    op.create_index(
        "uq_material_template_manual_scope",
        "material_templates",
        [sa.text("lower(material_type)"), "printer_id", "nozzle_diameter_mm"],
        unique=True,
        postgresql_where=sa.text("source_cura_material_id IS NULL"),
    )
    op.create_unique_constraint(
        "uq_material_template_cura_source",
        "material_templates",
        ["source_workstation_agent_id", "source_cura_material_id"],
    )


def downgrade() -> None:
    """Remove Cura import provenance without changing template content."""

    op.drop_constraint(
        "uq_material_template_cura_source",
        "material_templates",
        type_="unique",
    )
    op.drop_index(
        "uq_material_template_manual_scope",
        table_name="material_templates",
        postgresql_where=sa.text("source_cura_material_id IS NULL"),
    )
    op.create_unique_constraint(
        "uq_material_template_scope",
        "material_templates",
        ["material_type", "printer_id", "nozzle_diameter_mm"],
    )
    op.drop_index(
        op.f("ix_material_templates_source_workstation_agent_id"),
        table_name="material_templates",
    )
    op.drop_constraint(
        "fk_material_templates_cura_source_agent",
        "material_templates",
        type_="foreignkey",
    )
    op.drop_column("material_templates", "source_cura_material_id")
    op.drop_column("material_templates", "source_workstation_agent_id")
