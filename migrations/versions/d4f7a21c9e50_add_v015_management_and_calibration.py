"""add v0.1.5 management metadata and dimensional calibration

Revision ID: d4f7a21c9e50
Revises: c7e4a19d2b63
Create Date: 2026-08-11 19:00:00.000000
"""

import json
import unicodedata
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "d4f7a21c9e50"
down_revision: str | None = "c7e4a19d2b63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalized_color(name: str) -> str:
    """Match the application color-name identity during migration backfill."""

    return unicodedata.normalize("NFKC", name).strip().casefold()


def upgrade() -> None:
    """Add remembered colors, editable metadata, and the seventh workflow step."""

    op.create_table(
        "filament_colors",
        sa.Column("name", sa.String(length=96), nullable=False),
        sa.Column("normalized_name", sa.String(length=96), nullable=False),
        sa.Column("color_hex", sa.String(length=6), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_filament_colors")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_filament_colors_normalized_name")),
    )
    connection = op.get_bind()
    products = connection.execute(
        sa.text("SELECT id, color_name, color_hex FROM filament_products ORDER BY created_at, id")
    ).mappings()
    remembered: dict[str, tuple[str, str]] = {}
    for product in products:
        normalized = _normalized_color(product["color_name"])
        if normalized not in remembered:
            selected_hex = (product["color_hex"] or "808080").upper()
            remembered[normalized] = (product["color_name"].strip(), selected_hex)
            connection.execute(
                sa.text(
                    """
                    INSERT INTO filament_colors
                      (id, name, normalized_name, color_hex, record_version)
                    VALUES (:id, :name, :normalized_name, :color_hex, 1)
                    """
                ),
                {
                    "id": uuid4(),
                    "name": product["color_name"].strip(),
                    "normalized_name": normalized,
                    "color_hex": selected_hex,
                },
            )
        display_name, selected_hex = remembered[normalized]
        connection.execute(
            sa.text("UPDATE filament_products SET color_name = :name, color_hex = :color_hex WHERE id = :id"),
            {"id": product["id"], "name": display_name, "color_hex": selected_hex},
        )

    for column in (
        sa.Column("manufacturer", sa.String(length=160), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("kinematics", sa.String(length=48), nullable=True),
        sa.Column("nozzle_material", sa.String(length=96), nullable=True),
        sa.Column("extruder_type", sa.String(length=96), nullable=True),
        sa.Column("klipper_version", sa.String(length=96), nullable=True),
        sa.Column("moonraker_version", sa.String(length=96), nullable=True),
        sa.Column("host_name", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_info_sync_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("printers", column)

    for column in (
        sa.Column("product_name", sa.String(length=160), nullable=True),
        sa.Column("shape", sa.String(length=32), nullable=True),
        sa.Column("magnetic", sa.Boolean(), nullable=True),
        sa.Column("flexible", sa.Boolean(), nullable=True),
    ):
        op.add_column("build_plates", column)

    op.execute(sa.text("UPDATE calibration_steps SET step_order = step_order + 100 WHERE step_order >= 5"))
    op.execute(sa.text("UPDATE calibration_steps SET step_order = 6 WHERE step_order = 105"))
    op.execute(sa.text("UPDATE calibration_steps SET step_order = 7 WHERE step_order = 106"))
    sessions = connection.execute(sa.text("SELECT id, status FROM calibration_sessions")).mappings()
    for session in sessions:
        historical = session["status"] in {"PUBLISHED", "CANCELLED"}
        connection.execute(
            sa.text(
                """
                INSERT INTO calibration_steps
                  (session_id, step_order, step_key, name, required, status, inputs,
                   result, artifact, affected_profile_fields, notes, record_version, id)
                VALUES
                  (:session_id, 5, 'dimensional', 'Size and Hole Calibration', :required,
                   :status, CAST(:inputs AS jsonb), CAST(:result AS jsonb), CAST(:artifact AS jsonb),
                   CAST(:outputs AS jsonb), :notes, 1, :id)
                """
            ),
            {
                "session_id": session["id"],
                "required": not historical,
                "status": "SKIPPED" if historical else "NOT_STARTED",
                "inputs": json.dumps({}),
                "result": json.dumps({}),
                "artifact": json.dumps({}),
                "outputs": json.dumps(["xy_offset", "hole_xy_offset"]),
                "notes": "Added by the v0.1.5 migration" if historical else None,
                "id": uuid4(),
            },
        )
    op.execute(
        sa.text(
            """
            UPDATE calibration_sessions
            SET status = 'IN_PROGRESS', record_version = record_version + 1
            WHERE status = 'READY_TO_PUBLISH'
            """
        )
    )


def downgrade() -> None:
    """Remove v0.1.5 metadata while preserving unrelated canonical records."""

    op.execute(sa.text("DELETE FROM calibration_steps WHERE step_key = 'dimensional'"))
    op.execute(sa.text("UPDATE calibration_steps SET step_order = step_order + 100 WHERE step_order >= 6"))
    op.execute(sa.text("UPDATE calibration_steps SET step_order = 5 WHERE step_order = 106"))
    op.execute(sa.text("UPDATE calibration_steps SET step_order = 6 WHERE step_order = 107"))
    for column_name in ("flexible", "magnetic", "shape", "product_name"):
        op.drop_column("build_plates", column_name)
    for column_name in (
        "last_info_sync_at",
        "notes",
        "host_name",
        "moonraker_version",
        "klipper_version",
        "extruder_type",
        "nozzle_material",
        "kinematics",
        "model",
        "manufacturer",
    ):
        op.drop_column("printers", column_name)
    op.drop_table("filament_colors")
