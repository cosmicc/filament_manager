"""add atomic Cura takeover mappings

Revision ID: d0e1f2a3b456
Revises: c9d0e1f2a345
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b456"
down_revision: str | None = "c9d0e1f2a345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record takeover mappings and adopt the direct-save current snapshots."""

    op.create_table(
        "cura_takeover_mappings",
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("applied_template_revision_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["workstation_agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["material_templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["applied_template_revision_id"],
            ["material_template_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "source_id", name="uq_cura_takeover_mapping_source"),
        sa.UniqueConstraint("agent_id", "template_id", name="uq_cura_takeover_mapping_template"),
    )
    op.create_index(
        "ix_cura_takeover_mapping_agent_created",
        "cura_takeover_mappings",
        ["agent_id", "created_at"],
    )
    # Drafts were an operator-facing workflow before this release.  Preserve
    # the newest pending work as the current snapshot instead of discarding it
    # when direct saves become authoritative.  PostgreSQL's built-in md5 is
    # used only as a migration placeholder; the next direct save writes the
    # regular SHA-256 content checksum.
    op.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (material_template_id) id, status
            FROM material_template_revisions
            ORDER BY material_template_id, version DESC
        )
        UPDATE material_template_revisions AS revision
        SET status = CAST('PUBLISHED' AS profile_status),
            published_at = COALESCE(revision.published_at, CURRENT_TIMESTAMP),
            checksum = COALESCE(
                revision.checksum,
                md5(revision.id::text || revision.settings::text)
                || md5(revision.settings::text || revision.id::text)
            ),
            record_version = revision.record_version + 1
        FROM latest
        WHERE revision.id = latest.id
          AND latest.status IN (
              CAST('DRAFT' AS profile_status),
              CAST('VALIDATED' AS profile_status)
          )
        """
    )
    op.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (
                filament_product_id, printer_id, nozzle_diameter_mm
            ) id, status
            FROM material_profiles
            ORDER BY filament_product_id, printer_id, nozzle_diameter_mm, version DESC
        )
        UPDATE material_profiles AS profile
        SET status = CAST('PUBLISHED' AS profile_status),
            published_at = COALESCE(profile.published_at, CURRENT_TIMESTAMP),
            checksum = COALESCE(
                profile.checksum,
                md5(profile.id::text || profile.version::text)
                || md5(profile.version::text || profile.id::text)
            ),
            record_version = profile.record_version + 1
        FROM latest
        WHERE profile.id = latest.id
          AND latest.status IN (
              CAST('DRAFT' AS profile_status),
              CAST('VALIDATED' AS profile_status)
          )
        """
    )


def downgrade() -> None:
    """Remove takeover provenance without reverting adopted current settings."""

    op.drop_index(
        "ix_cura_takeover_mapping_agent_created",
        table_name="cura_takeover_mappings",
    )
    op.drop_table("cura_takeover_mappings")
