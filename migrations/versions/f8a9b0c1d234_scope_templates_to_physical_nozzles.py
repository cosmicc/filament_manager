"""scope templates to printer-owned physical nozzles

Revision ID: f8a9b0c1d234
Revises: e7f8a9b0c123
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d234"
down_revision: str | None = "e7f8a9b0c123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Assign every nozzle to a printer and every template to one exact nozzle."""

    op.add_column("nozzles", sa.Column("printer_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_nozzles_printer_id",
        "nozzles",
        "printers",
        ["printer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        UPDATE nozzles AS nozzle
        SET printer_id = printer.id
        FROM printers AS printer
        WHERE printer.active_nozzle_id = nozzle.id
          AND nozzle.printer_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE nozzles AS nozzle
        SET printer_id = latest.printer_id
        FROM (
            SELECT DISTINCT ON (nozzle_id) nozzle_id, printer_id
            FROM nozzle_lifecycle_events
            WHERE printer_id IS NOT NULL
            ORDER BY nozzle_id, occurred_at DESC, id DESC
        ) AS latest
        WHERE latest.nozzle_id = nozzle.id
          AND nozzle.printer_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE nozzles
        SET printer_id = (SELECT id FROM printers ORDER BY created_at, id LIMIT 1)
        WHERE printer_id IS NULL
          AND (SELECT count(*) FROM printers) = 1
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM nozzles WHERE printer_id IS NULL) THEN
                RAISE EXCEPTION 'Cannot assign every existing nozzle to a printer; install or record each nozzle on its owner printer before upgrading';
            END IF;
        END $$
        """
    )
    op.alter_column("nozzles", "printer_id", nullable=False)
    op.drop_constraint("uq_nozzles_nozzle_code", "nozzles", type_="unique")
    op.create_index("ix_nozzles_printer_id", "nozzles", ["printer_id"])
    op.create_index(
        "uq_nozzles_printer_code",
        "nozzles",
        ["printer_id", sa.text("lower(nozzle_code)")],
        unique=True,
    )

    op.add_column("material_templates", sa.Column("nozzle_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_material_templates_nozzle_id",
        "material_templates",
        "nozzles",
        ["nozzle_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        UPDATE material_templates AS template
        SET nozzle_id = printer.active_nozzle_id
        FROM printers AS printer, nozzles AS nozzle
        WHERE printer.id = template.printer_id
          AND nozzle.id = printer.active_nozzle_id
          AND nozzle.diameter_mm = template.nozzle_diameter_mm
          AND template.nozzle_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE material_templates AS template
        SET nozzle_id = (
            SELECT nozzle.id
            FROM nozzles AS nozzle
            LEFT JOIN nozzle_lifecycle_events AS event ON event.nozzle_id = nozzle.id
            WHERE nozzle.printer_id = template.printer_id
              AND nozzle.diameter_mm = template.nozzle_diameter_mm
            ORDER BY event.occurred_at DESC NULLS LAST, nozzle.created_at, nozzle.id
            LIMIT 1
        )
        WHERE template.nozzle_id IS NULL
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM material_templates WHERE nozzle_id IS NULL) THEN
                RAISE EXCEPTION 'Cannot map every material template to an exact printer-owned nozzle; add a matching physical nozzle before upgrading';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM material_templates
                WHERE active
                GROUP BY lower(material_type), nozzle_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Multiple active templates exist for the same material and physical nozzle; deactivate duplicates before upgrading';
            END IF;
        END $$
        """
    )
    op.alter_column("material_templates", "nozzle_id", nullable=False)
    op.create_index("ix_material_templates_nozzle_id", "material_templates", ["nozzle_id"])
    op.drop_index("uq_material_template_manual_scope", table_name="material_templates")
    op.create_index(
        "uq_material_template_active_nozzle_scope",
        "material_templates",
        [sa.text("lower(material_type)"), "nozzle_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    """Restore diameter-only template scoping and globally unique nozzle codes."""

    op.drop_index("uq_material_template_active_nozzle_scope", table_name="material_templates")
    op.create_index(
        "uq_material_template_manual_scope",
        "material_templates",
        [sa.text("lower(material_type)"), "printer_id", "nozzle_diameter_mm"],
        unique=True,
        postgresql_where=sa.text("source_cura_material_id IS NULL"),
    )
    op.drop_index("ix_material_templates_nozzle_id", table_name="material_templates")
    op.drop_constraint("fk_material_templates_nozzle_id", "material_templates", type_="foreignkey")
    op.drop_column("material_templates", "nozzle_id")

    op.drop_index("uq_nozzles_printer_code", table_name="nozzles")
    op.drop_index("ix_nozzles_printer_id", table_name="nozzles")
    op.create_unique_constraint("uq_nozzles_nozzle_code", "nozzles", ["nozzle_code"])
    op.drop_constraint("fk_nozzles_printer_id", "nozzles", type_="foreignkey")
    op.drop_column("nozzles", "printer_id")
