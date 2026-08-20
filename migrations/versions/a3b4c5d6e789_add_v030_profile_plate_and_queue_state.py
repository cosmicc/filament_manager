"""add v0.3.0 material, build-plate image, and queue state

Revision ID: a3b4c5d6e789
Revises: f2a3b4c5d678
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e789"
down_revision: str | None = "f2a3b4c5d678"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add independently tracked prime speed, plate images, and resolved queue history."""

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'SUPERSEDED'")
    op.add_column(
        "material_profiles",
        sa.Column("retraction_prime_speed_mm_s", sa.Numeric(12, 5), nullable=True),
    )
    op.execute(
        "UPDATE material_profiles "
        "SET retraction_prime_speed_mm_s = retraction_speed_mm_s, "
        "setting_overrides = CASE "
        "WHEN setting_overrides ? 'retraction_speed_mm_s' "
        "THEN jsonb_set(setting_overrides, '{retraction_prime_speed_mm_s}', "
        "setting_overrides->'retraction_speed_mm_s', true) "
        "ELSE setting_overrides END "
        "WHERE retraction_prime_speed_mm_s IS NULL"
    )
    op.execute(
        "UPDATE material_profiles SET cura_extensions = cura_extensions - 'cool_fan_speed_0', "
        "cura_extensions_schema_version = 2"
    )
    op.execute(
        "UPDATE material_template_revisions "
        "SET settings = jsonb_set("
        "jsonb_set(settings - 'cool_fan_speed_0', "
        "'{cura_extensions}', COALESCE(settings->'cura_extensions', '{}'::jsonb) - 'cool_fan_speed_0'), "
        "'{retraction_prime_speed_mm_s}', "
        "COALESCE(settings->'retraction_prime_speed_mm_s', settings->'retraction_speed_mm_s', 'null'::jsonb), "
        "true)"
    )

    op.add_column("build_plates", sa.Column("image_data", sa.LargeBinary(), nullable=True))
    op.add_column("build_plates", sa.Column("image_media_type", sa.String(length=32), nullable=True))
    op.add_column("build_plates", sa.Column("image_sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "build_plates",
        sa.Column("image_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )

    op.execute(
        "UPDATE outbox_jobs SET status = 'SUPERSEDED', completed_at = COALESCE(completed_at, NOW()) "
        "WHERE status = 'DEAD' AND idempotency_key LIKE 'periodic:%'"
    )
    # Multicolor palettes are product-owned. Existing products already retain
    # their complete mirrored palettes, so these obsolete shared rows are safe
    # to discard and must not reappear in the color-name picker.
    op.execute("DELETE FROM filament_colors WHERE color_mode = 'multicolor'")


def downgrade() -> None:
    """Remove v0.3.0 columns while retaining the harmless PostgreSQL enum value."""

    op.execute("UPDATE outbox_jobs SET status = 'DEAD' WHERE status = 'SUPERSEDED'")
    op.drop_column("build_plates", "image_version")
    op.drop_column("build_plates", "image_sha256")
    op.drop_column("build_plates", "image_media_type")
    op.drop_column("build_plates", "image_data")
    op.drop_column("material_profiles", "retraction_prime_speed_mm_s")
