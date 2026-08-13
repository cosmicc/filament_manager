"""add profile inheritance and Cura edit receipts

Revision ID: a7b8c9d0e123
Revises: f6a7b8c9d012
Create Date: 2026-08-13
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e123"
down_revision: str | None = "f6a7b8c9d012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROFILE_SETTING_KEYS = (
    "chamber_temp_c",
    "extruder_temp_c",
    "bed_temp_c",
    "flow_percent",
    "print_speed_mm_s",
    "outer_wall_speed_mm_s",
    "inner_wall_speed_mm_s",
    "infill_speed_mm_s",
    "top_bottom_speed_mm_s",
    "initial_layer_speed_mm_s",
    "travel_speed_mm_s",
    "support_speed_mm_s",
    "retraction_distance_mm",
    "retraction_speed_mm_s",
    "cooling_enabled",
    "cooling_min_percent",
    "cooling_max_percent",
    "support_overhang_angle_deg",
    "tree_max_branch_angle_deg",
    "pressure_advance",
    "filament_density_g_cm3",
    "preferred_build_plate_surface_id",
)
NUMERIC_TEXT = re.compile(r"^-?\d+(?:\.\d+)?$")


def _plain(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    return value


def _equivalent(left: object, right: object) -> bool:
    left = _plain(left)
    right = _plain(right)
    if left == right:
        return True
    if isinstance(left, str) and isinstance(right, str):
        if NUMERIC_TEXT.fullmatch(left) and NUMERIC_TEXT.fullmatch(right):
            try:
                return Decimal(left) == Decimal(right)
            except InvalidOperation:
                return False
    return False


def _snapshot(row: sa.RowMapping) -> dict[str, object]:
    values = {key: _plain(row[key]) for key in PROFILE_SETTING_KEYS}
    values["cura_extensions"] = dict(row["cura_extensions"] or {})
    return values


def _overrides(base: dict[str, object], desired: dict[str, object]) -> dict[str, object]:
    result = {
        key: desired.get(key)
        for key in PROFILE_SETTING_KEYS
        if not _equivalent(base.get(key), desired.get(key))
    }
    base_extensions = base.get("cura_extensions", {})
    desired_extensions = desired.get("cura_extensions", {})
    if not isinstance(base_extensions, dict):
        base_extensions = {}
    if not isinstance(desired_extensions, dict):
        desired_extensions = {}
    extension_changes: dict[str, object] = {}
    for key in sorted(set(base_extensions) | set(desired_extensions)):
        if not _equivalent(base_extensions.get(key), desired_extensions.get(key)):
            extension_changes[key] = desired_extensions.get(key) if key in desired_extensions else None
    if extension_changes:
        result["cura_extensions"] = extension_changes
    return result


def _published_template_revision(
    connection: sa.Connection,
    *,
    material_type: str,
    printer_id: object,
    nozzle_diameter_mm: object,
    filament_diameter_mm: object,
    fallback_settings: dict[str, object],
) -> tuple[object, dict[str, object]]:
    """Find or create a published base for one legacy unlinked profile."""

    template = (
        connection.execute(
            sa.text(
                """
            SELECT id
            FROM material_templates
            WHERE lower(material_type) = lower(:material_type)
              AND printer_id = :printer_id
              AND nozzle_diameter_mm = :nozzle_diameter_mm
            ORDER BY active DESC, created_at
            LIMIT 1
            """
            ),
            {
                "material_type": material_type,
                "printer_id": printer_id,
                "nozzle_diameter_mm": nozzle_diameter_mm,
            },
        )
        .mappings()
        .first()
    )
    now = datetime.now(UTC)
    if template is None:
        template_id = uuid4()
        connection.execute(
            sa.text(
                """
                INSERT INTO material_templates (
                    id, name, material_type, description, printer_id,
                    nozzle_diameter_mm, filament_diameter_mm, active,
                    record_version, created_at, updated_at
                ) VALUES (
                    :id, :name, :material_type, :description, :printer_id,
                    :nozzle_diameter_mm, :filament_diameter_mm, true,
                    1, :now, :now
                )
                """
            ),
            {
                "id": template_id,
                "name": f"Template {material_type}",
                "material_type": material_type,
                "description": "Created during the 0.2.0 profile-inheritance migration.",
                "printer_id": printer_id,
                "nozzle_diameter_mm": nozzle_diameter_mm,
                "filament_diameter_mm": filament_diameter_mm,
                "now": now,
            },
        )
    else:
        template_id = template["id"]

    published = (
        connection.execute(
            sa.text(
                """
            SELECT id, settings
            FROM material_template_revisions
            WHERE material_template_id = :template_id
              AND status = CAST('PUBLISHED' AS profile_status)
            ORDER BY version DESC
            LIMIT 1
            """
            ),
            {"template_id": template_id},
        )
        .mappings()
        .first()
    )
    if published is not None:
        return published["id"], dict(published["settings"])

    latest_version = connection.scalar(
        sa.text(
            "SELECT COALESCE(MAX(version), 0) FROM material_template_revisions "
            "WHERE material_template_id = :template_id"
        ),
        {"template_id": template_id},
    )
    revision_id = uuid4()
    version = int(latest_version or 0) + 1
    checksum_payload = {
        "material_template_id": str(template_id),
        "version": version,
        "settings": fallback_settings,
    }
    checksum = hashlib.sha256(
        json.dumps(checksum_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    connection.execute(
        sa.text(
            """
            INSERT INTO material_template_revisions (
                id, material_template_id, version, status, settings,
                checksum, published_at, record_version, created_at, updated_at
            ) VALUES (
                :id, :template_id, :version, CAST('PUBLISHED' AS profile_status),
                CAST(:settings AS jsonb), :checksum, :now, 1, :now, :now
            )
            """
        ),
        {
            "id": revision_id,
            "template_id": template_id,
            "version": version,
            "settings": json.dumps(fallback_settings, sort_keys=True),
            "checksum": checksum,
            "now": now,
        },
    )
    return revision_id, fallback_settings


def upgrade() -> None:
    """Add sparse overrides, link legacy profiles, and track imported Cura edits."""

    op.add_column(
        "material_profiles",
        sa.Column(
            "setting_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_table(
        "cura_managed_edit_receipts",
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.String(length=96), nullable=False),
        sa.Column("material_guid", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_revision_id", sa.Uuid(), nullable=False),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_profile_revision_id", sa.Uuid(), nullable=True),
        sa.Column("created_template_revision_id", sa.Uuid(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["workstation_agents.id"],
            name=op.f("fk_cura_managed_edit_receipts_agent_id_workstation_agents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_profile_revision_id"],
            ["material_profiles.id"],
            name=op.f("fk_cura_managed_edit_receipts_created_profile_revision_id_material_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_template_revision_id"],
            ["material_template_revisions.id"],
            name=op.f(
                "fk_cura_managed_edit_receipts_created_template_revision_id_material_template_revisions"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cura_managed_edit_receipts")),
        sa.UniqueConstraint(
            "material_guid",
            "content_checksum",
            name="uq_cura_managed_edit_receipt_content",
        ),
    )
    op.create_index(
        op.f("ix_cura_managed_edit_receipts_agent_id"),
        "cura_managed_edit_receipts",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_cura_managed_edit_receipt_source",
        "cura_managed_edit_receipts",
        ["source_kind", "source_revision_id"],
        unique=False,
    )

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE material_templates SET name = 'Template ' || material_type"))
    profiles = connection.execute(
        sa.text(
            """
            SELECT mp.*, fp.material_type, fp.diameter_mm
            FROM material_profiles AS mp
            JOIN filament_products AS fp ON fp.id = mp.filament_product_id
            ORDER BY mp.created_at, mp.id
            """
        )
    ).mappings()
    for row in profiles:
        desired = _snapshot(row)
        base_revision_id = row["source_template_revision_id"]
        base_settings: dict[str, object] | None = None
        if base_revision_id is not None:
            stored = connection.scalar(
                sa.text("SELECT settings FROM material_template_revisions WHERE id = :id"),
                {"id": base_revision_id},
            )
            if isinstance(stored, dict):
                base_settings = dict(stored)
        if base_settings is None:
            base_revision_id, base_settings = _published_template_revision(
                connection,
                material_type=str(row["material_type"]),
                printer_id=row["printer_id"],
                nozzle_diameter_mm=row["nozzle_diameter_mm"],
                filament_diameter_mm=row["diameter_mm"],
                fallback_settings=desired,
            )
            connection.execute(
                sa.text(
                    "UPDATE filament_products SET source_template_revision_id = COALESCE("
                    "source_template_revision_id, :base_id) WHERE id = :product_id"
                ),
                {"base_id": base_revision_id, "product_id": row["filament_product_id"]},
            )
        connection.execute(
            sa.text(
                """
                UPDATE material_profiles
                SET source_template_revision_id = :base_id,
                    setting_overrides = CAST(:overrides AS jsonb)
                WHERE id = :profile_id
                """
            ),
            {
                "base_id": base_revision_id,
                "overrides": json.dumps(_overrides(base_settings, desired), sort_keys=True),
                "profile_id": row["id"],
            },
        )
    profile_template_fk = op.f("fk_material_profiles_source_template_revision_id_material_template_revisions")
    op.drop_constraint(profile_template_fk, "material_profiles", type_="foreignkey")
    op.create_foreign_key(
        profile_template_fk,
        "material_profiles",
        "material_template_revisions",
        ["source_template_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column(
        "material_profiles",
        "source_template_revision_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.alter_column("material_profiles", "setting_overrides", server_default=None)


def downgrade() -> None:
    """Remove sparse inheritance metadata while retaining resolved profile snapshots."""

    profile_template_fk = op.f("fk_material_profiles_source_template_revision_id_material_template_revisions")
    op.alter_column(
        "material_profiles",
        "source_template_revision_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.drop_constraint(profile_template_fk, "material_profiles", type_="foreignkey")
    op.create_foreign_key(
        profile_template_fk,
        "material_profiles",
        "material_template_revisions",
        ["source_template_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index(
        "ix_cura_managed_edit_receipt_source",
        table_name="cura_managed_edit_receipts",
    )
    op.drop_index(
        op.f("ix_cura_managed_edit_receipts_agent_id"),
        table_name="cura_managed_edit_receipts",
    )
    op.drop_table("cura_managed_edit_receipts")
    op.drop_column("material_profiles", "setting_overrides")
