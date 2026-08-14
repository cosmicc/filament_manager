"""add print history and GUI follow-up foundations

Revision ID: b8c9d0e1f234
Revises: a7b8c9d0e123
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f234"
down_revision: str | None = "a7b8c9d0e123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable print/maintenance history and operational UI state."""

    print_job_status = postgresql.ENUM(
        "IN_PROGRESS",
        "COMPLETED",
        "CANCELLED",
        "FAILED",
        "LEGACY_UNKNOWN",
        name="print_job_status",
        create_type=False,
    )
    inspection_status = postgresql.ENUM(
        "PENDING",
        "PASSED",
        "WARNING",
        "BLOCKED",
        "UNAVAILABLE",
        name="gcode_inspection_status",
        create_type=False,
    )
    quality_rating = postgresql.ENUM(
        "FAILED",
        "ACCEPTABLE",
        "SUCCESSFUL",
        "EXCELLENT",
        name="print_quality_rating",
        create_type=False,
    )
    maintenance_type = postgresql.ENUM(
        "CLEANED",
        "MESH_CALIBRATED",
        name="plate_maintenance_type",
        create_type=False,
    )
    notification_severity = postgresql.ENUM(
        "INFO", "WARNING", "ERROR", name="notification_severity", create_type=False
    )
    bind = op.get_bind()
    print_job_status.create(bind, checkfirst=True)
    inspection_status.create(bind, checkfirst=True)
    quality_rating.create(bind, checkfirst=True)
    maintenance_type.create(bind, checkfirst=True)
    notification_severity.create(bind, checkfirst=True)

    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    for column in (
        sa.Column("print_history_initialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_print_history_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_print_history_end_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("printers", column)
    for column in (
        sa.Column("cleaning_due_after_prints", sa.Integer(), server_default="10", nullable=False),
        sa.Column("cleaning_due_after_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("mesh_due_after_prints", sa.Integer(), server_default="30", nullable=False),
        sa.Column("mesh_due_after_days", sa.Integer(), server_default="30", nullable=False),
    ):
        op.add_column("build_plates", column)

    op.create_table(
        "application_settings",
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_application_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_settings")),
        sa.UniqueConstraint("key", name=op.f("uq_application_settings_key")),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO application_settings
              (id, key, value, record_version)
            VALUES
              (gen_random_uuid(), 'gcode_inspection', '{"policy":"warn"}'::jsonb, 1)
            """
        )
    )

    op.create_table(
        "print_jobs",
        sa.Column("printer_id", sa.UUID(), nullable=False),
        sa.Column("moonraker_job_id", sa.String(length=160), nullable=True),
        sa.Column("moonraker_file_uuid", sa.String(length=96), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("gcode_sha256", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", print_job_status, nullable=False),
        sa.Column("spool_id", sa.UUID(), nullable=True),
        sa.Column("filament_product_id", sa.UUID(), nullable=True),
        sa.Column("material_profile_id", sa.UUID(), nullable=True),
        sa.Column("material_profile_version", sa.Integer(), nullable=True),
        sa.Column("build_plate_id", sa.UUID(), nullable=True),
        sa.Column("build_plate_surface_id", sa.UUID(), nullable=True),
        sa.Column("nozzle_diameter_mm", sa.Numeric(14, 5), nullable=True),
        sa.Column("material_guid", sa.String(length=96), nullable=True),
        sa.Column("material_name", sa.String(length=255), nullable=True),
        sa.Column("material_type", sa.String(length=96), nullable=True),
        sa.Column("state_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inspection_status", inspection_status, nullable=False),
        sa.Column("inspection_policy", sa.String(length=16), nullable=False),
        sa.Column("inspection", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slicer", sa.String(length=96), nullable=True),
        sa.Column("slicer_version", sa.String(length=96), nullable=True),
        sa.Column("cura_quality_profile", sa.String(length=255), nullable=True),
        sa.Column("layer_height_mm", sa.Numeric(14, 5), nullable=True),
        sa.Column("line_width_mm", sa.Numeric(14, 5), nullable=True),
        sa.Column("extruder_temp_c", sa.Numeric(14, 5), nullable=True),
        sa.Column("bed_temp_c", sa.Numeric(14, 5), nullable=True),
        sa.Column("chamber_temp_c", sa.Numeric(14, 5), nullable=True),
        sa.Column("print_speed_mm_s", sa.Numeric(14, 5), nullable=True),
        sa.Column("pressure_advance", sa.Numeric(14, 5), nullable=True),
        sa.Column("retraction_distance_mm", sa.Numeric(14, 5), nullable=True),
        sa.Column("retraction_speed_mm_s", sa.Numeric(14, 5), nullable=True),
        sa.Column("flow_percent", sa.Numeric(14, 5), nullable=True),
        sa.Column("predicted_filament_length_mm", sa.Numeric(14, 5), nullable=True),
        sa.Column("predicted_filament_weight_g", sa.Numeric(14, 5), nullable=True),
        sa.Column("actual_filament_length_mm", sa.Numeric(14, 5), nullable=True),
        sa.Column("actual_filament_weight_g", sa.Numeric(14, 5), nullable=True),
        sa.Column("estimated_duration_seconds", sa.Numeric(14, 3), nullable=True),
        sa.Column("print_duration_seconds", sa.Numeric(14, 3), nullable=True),
        sa.Column("total_duration_seconds", sa.Numeric(14, 3), nullable=True),
        sa.Column("support_configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("machine_name", sa.String(length=255), nullable=True),
        sa.Column("timelapse_url", sa.String(length=1024), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["printer_id"],
            ["printers.id"],
            name=op.f("fk_print_jobs_printer_id_printers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["spool_id"], ["spools.id"], name=op.f("fk_print_jobs_spool_id_spools"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["filament_product_id"],
            ["filament_products.id"],
            name=op.f("fk_print_jobs_filament_product_id_filament_products"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["material_profile_id"],
            ["material_profiles.id"],
            name=op.f("fk_print_jobs_material_profile_id_material_profiles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["build_plate_id"],
            ["build_plates.id"],
            name=op.f("fk_print_jobs_build_plate_id_build_plates"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["build_plate_surface_id"],
            ["build_plate_surfaces.id"],
            name=op.f("fk_print_jobs_build_plate_surface_id_build_plate_surfaces"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_jobs")),
        sa.UniqueConstraint("printer_id", "moonraker_job_id", name="uq_print_job_moonraker"),
    )
    op.create_index("ix_print_jobs_printer_id", "print_jobs", ["printer_id"])
    op.create_index("ix_print_jobs_material_profile_id", "print_jobs", ["material_profile_id"])
    op.create_index("ix_print_jobs_started_at", "print_jobs", ["started_at"])
    op.create_index("ix_print_jobs_profile_status", "print_jobs", ["material_profile_id", "status"])

    op.create_table(
        "print_material_segments",
        sa.Column("print_job_id", sa.UUID(), nullable=False),
        sa.Column("segment_number", sa.Integer(), nullable=False),
        sa.Column("spool_id", sa.UUID(), nullable=True),
        sa.Column("filament_product_id", sa.UUID(), nullable=True),
        sa.Column("material_profile_id", sa.UUID(), nullable=True),
        sa.Column("material_profile_version", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("state_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_filament_length_mm", sa.Numeric(14, 5), nullable=True),
        sa.Column("actual_filament_weight_g", sa.Numeric(14, 5), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["print_job_id"],
            ["print_jobs.id"],
            name=op.f("fk_print_material_segments_print_job_id_print_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["spool_id"],
            ["spools.id"],
            name=op.f("fk_print_material_segments_spool_id_spools"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["filament_product_id"],
            ["filament_products.id"],
            name=op.f("fk_print_material_segments_filament_product_id_filament_products"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["material_profile_id"],
            ["material_profiles.id"],
            name=op.f("fk_print_material_segments_material_profile_id_material_profiles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_material_segments")),
        sa.UniqueConstraint("print_job_id", "segment_number", name="uq_print_material_segment_number"),
    )
    op.create_index("ix_print_segments_spool_time", "print_material_segments", ["spool_id", "started_at"])

    op.create_table(
        "print_assessments",
        sa.Column("print_job_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("rating", quality_rating, nullable=False),
        sa.Column("defect_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("assessed_by", sa.UUID(), nullable=False),
        sa.Column("supersedes_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["print_job_id"],
            ["print_jobs.id"],
            name=op.f("fk_print_assessments_print_job_id_print_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assessed_by"],
            ["users.id"],
            name=op.f("fk_print_assessments_assessed_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["print_assessments.id"],
            name=op.f("fk_print_assessments_supersedes_id_print_assessments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_assessments")),
        sa.UniqueConstraint("print_job_id", "revision", name="uq_print_assessment_revision"),
    )
    op.create_index("ix_print_assessments_job_created", "print_assessments", ["print_job_id", "created_at"])

    op.create_table(
        "build_plate_maintenance_events",
        sa.Column("build_plate_id", sa.UUID(), nullable=False),
        sa.Column("build_plate_surface_id", sa.UUID(), nullable=True),
        sa.Column("maintenance_type", maintenance_type, nullable=False),
        sa.Column("performed_by", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["build_plate_id"],
            ["build_plates.id"],
            name=op.f("fk_build_plate_maintenance_events_build_plate_id_build_plates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["build_plate_surface_id"],
            ["build_plate_surfaces.id"],
            name=op.f("fk_build_plate_maintenance_events_build_plate_surface_id_build_plate_surfaces"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"],
            ["users.id"],
            name=op.f("fk_build_plate_maintenance_events_performed_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_build_plate_maintenance_events")),
    )
    op.create_index(
        "ix_plate_maintenance_plate_time", "build_plate_maintenance_events", ["build_plate_id", "occurred_at"]
    )
    op.execute(
        sa.text(
            """
            INSERT INTO build_plate_maintenance_events
              (id, build_plate_id, maintenance_type, source, notes, occurred_at)
            SELECT gen_random_uuid(), id, 'CLEANED', 'migration',
                   'Imported from the pre-0.2.1 last-cleaned timestamp', last_cleaned_at
            FROM build_plates WHERE last_cleaned_at IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO build_plate_maintenance_events
              (id, build_plate_id, build_plate_surface_id, maintenance_type, source, notes, occurred_at)
            SELECT gen_random_uuid(), build_plate_id, id, 'MESH_CALIBRATED', 'migration',
                   'Imported from the pre-0.2.1 mesh-calibration timestamp', last_mesh_calibrated_at
            FROM build_plate_surfaces WHERE last_mesh_calibrated_at IS NOT NULL
            """
        )
    )

    op.create_table(
        "notifications",
        sa.Column("deduplication_key", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", notification_severity, nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("action_path", sa.String(length=255), nullable=True),
        sa.Column("object_type", sa.String(length=64), nullable=True),
        sa.Column("object_id", sa.UUID(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("deduplication_key", name=op.f("uq_notifications_deduplication_key")),
    )
    op.create_index("ix_notifications_active_time", "notifications", ["active", "last_seen_at"])
    op.create_table(
        "user_notification_states",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_user_notification_states_notification_id_notifications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_notification_states_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "notification_id", name=op.f("pk_user_notification_states")),
    )


def downgrade() -> None:
    """Remove v0.2.1 foundations without changing older canonical data."""

    op.drop_table("user_notification_states")
    op.drop_index("ix_notifications_active_time", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_plate_maintenance_plate_time", table_name="build_plate_maintenance_events")
    op.drop_table("build_plate_maintenance_events")
    op.drop_index("ix_print_assessments_job_created", table_name="print_assessments")
    op.drop_table("print_assessments")
    op.drop_index("ix_print_segments_spool_time", table_name="print_material_segments")
    op.drop_table("print_material_segments")
    op.drop_index("ix_print_jobs_profile_status", table_name="print_jobs")
    op.drop_index("ix_print_jobs_started_at", table_name="print_jobs")
    op.drop_index("ix_print_jobs_material_profile_id", table_name="print_jobs")
    op.drop_index("ix_print_jobs_printer_id", table_name="print_jobs")
    op.drop_table("print_jobs")
    op.drop_table("application_settings")
    for column_name in (
        "mesh_due_after_days",
        "mesh_due_after_prints",
        "cleaning_due_after_days",
        "cleaning_due_after_prints",
    ):
        op.drop_column("build_plates", column_name)
    for column_name in (
        "last_print_history_end_at",
        "last_print_history_sync_at",
        "print_history_initialized_at",
    ):
        op.drop_column("printers", column_name)
    op.drop_column("users", "must_change_password")
    bind = op.get_bind()
    for enum_name in (
        "notification_severity",
        "plate_maintenance_type",
        "print_quality_rating",
        "gcode_inspection_status",
        "print_job_status",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
