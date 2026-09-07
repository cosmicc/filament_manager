"""Remove plate cleaning and retain automatic mesh/selection evidence.

Revision ID: a5b6c7d8e901
Revises: f4a5b6c7d890
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op

revision = "a5b6c7d8e901"
down_revision = "f4a5b6c7d890"
branch_labels = None
depends_on = None


def _replace_event_enum(include_cleaning: bool) -> None:
    """Replace the enum transactionally after removing obsolete typed rows."""

    op.execute("ALTER TYPE plate_maintenance_type RENAME TO plate_maintenance_type_legacy_v073")
    labels = "'CLEANED', 'MESH_CALIBRATED'" if include_cleaning else "'MESH_CALIBRATED'"
    op.execute(f"CREATE TYPE plate_maintenance_type AS ENUM ({labels})")
    op.execute("""ALTER TABLE build_plate_maintenance_events ALTER COLUMN maintenance_type
        TYPE plate_maintenance_type USING maintenance_type::text::plate_maintenance_type""")
    op.execute("DROP TYPE plate_maintenance_type_legacy_v073")


def upgrade() -> None:
    """Remove only cleaning data; keep mesh evidence and immutable print snapshots."""

    op.execute("""DELETE FROM audit_events WHERE action = 'build_plate.maintenance'
        AND ("after"->>'maintenance_type' = 'cleaned'
             OR ("after"->>'cleaned' = 'true' AND COALESCE("after"->>'mesh_calibrated', 'false') != 'true'))""")
    op.execute("""UPDATE audit_events SET "after" = "after" - 'cleaned'
        WHERE action = 'build_plate.maintenance' AND "after" ? 'cleaned'""")
    op.execute("DELETE FROM build_plate_maintenance_events WHERE maintenance_type::text = 'CLEANED'")
    op.execute("""DELETE FROM notifications WHERE category = 'plate_maintenance_due'
        AND deduplication_key ~ '^plate:[0-9a-f-]+[:]cleaning-due$'""")
    _replace_event_enum(False)
    for field in ("last_cleaned_at", "cleaning_due_after_prints", "cleaning_due_after_days"):
        op.drop_column("build_plates", field)
    op.add_column("build_plates", sa.Column("last_activated_at", sa.DateTime(timezone=True)))
    op.add_column("build_plate_surfaces", sa.Column("last_activated_at", sa.DateTime(timezone=True)))
    op.add_column("build_plate_surfaces", sa.Column("last_mesh_observed_at", sa.DateTime(timezone=True)))
    for table, column in (
        ("build_plate_surfaces", "mesh_calibration_sequence"),
        ("printers", "plate_selection_sequence"),
    ):
        op.add_column(table, sa.Column(column, sa.BigInteger(), nullable=False, server_default="0"))
        op.alter_column(table, column, server_default=None)
    op.add_column(
        "printers",
        sa.Column("plate_selection_initialized", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE printers SET plate_selection_initialized = true WHERE active_plate_surface_id IS NOT NULL"
    )
    op.alter_column("printers", "plate_selection_initialized", server_default=None)
    # Reconstruct dates only from recorded identity transitions, never migration time.
    for table, key in (
        ("build_plates", "active_plate_id"),
        ("build_plate_surfaces", "active_plate_surface_id"),
    ):
        # Only fixed table/column identifiers above enter this SQL.
        op.execute(
            sa.text(f"""UPDATE {table} AS target SET last_activated_at = evidence.occurred_at
            FROM (SELECT "after"->>'{key}' AS identity, max(occurred_at) AS occurred_at
                  FROM audit_events WHERE action IN ('build_plate.select', 'build_plate.synchronize')
                  AND "after"->>'{key}' IS NOT NULL
                  AND "before"->>'{key}' IS DISTINCT FROM "after"->>'{key}'
                  GROUP BY "after"->>'{key}') AS evidence
            WHERE target.id::text = evidence.identity""")  # noqa: S608 - fixed identifiers above
        )


def downgrade() -> None:
    """Restore the old schema only; deleted cleaning history requires a backup."""

    _replace_event_enum(True)
    op.add_column("build_plates", sa.Column("last_cleaned_at", sa.DateTime(timezone=True)))
    for field, value in (("cleaning_due_after_prints", "10"), ("cleaning_due_after_days", "7")):
        op.add_column("build_plates", sa.Column(field, sa.Integer(), nullable=False, server_default=value))
        op.alter_column("build_plates", field, server_default=None)
    for table, fields in (
        ("build_plates", ("last_activated_at",)),
        ("build_plate_surfaces", ("last_activated_at", "last_mesh_observed_at", "mesh_calibration_sequence")),
        ("printers", ("plate_selection_initialized", "plate_selection_sequence")),
    ):
        for field in fields:
            op.drop_column(table, field)
