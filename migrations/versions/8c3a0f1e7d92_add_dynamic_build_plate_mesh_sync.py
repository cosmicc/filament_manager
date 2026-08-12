"""add dynamic build plate side and mesh synchronization

Revision ID: 8c3a0f1e7d92
Revises: 2f6e9d8c4b31
Create Date: 2026-08-11 10:00:00.000000
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8c3a0f1e7d92"
down_revision: str | None = "2f6e9d8c4b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Separate physical P-number plates from their printable A and B sides."""

    connection = op.get_bind()
    op.alter_column(
        "build_plates",
        "plate_code",
        existing_type=sa.String(length=2),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.create_check_constraint(
        op.f("ck_build_plates_build_plate_code_format"),
        "build_plates",
        "plate_code ~ '^P[1-9][0-9]*$'",
    )
    op.add_column("build_plates", sa.Column("description", sa.Text(), nullable=True))

    texture_enum = postgresql.ENUM("SMOOTH", "TEXTURED", name="plate_surface_texture")
    texture_enum.create(connection, checkfirst=True)
    op.create_table(
        "build_plate_surfaces",
        sa.Column("build_plate_id", sa.UUID(), nullable=False),
        sa.Column("side", sa.String(length=1), nullable=False),
        sa.Column("surface_code", sa.String(length=32), nullable=False),
        sa.Column("klipper_mesh_profile", sa.String(length=32), nullable=False),
        sa.Column("surface_material", sa.String(length=120), nullable=True),
        sa.Column(
            "texture",
            postgresql.ENUM(
                "SMOOTH",
                "TEXTURED",
                name="plate_surface_texture",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("mesh_available", sa.Boolean(), nullable=True),
        sa.Column("last_mesh_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_mesh_calibrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "side IN ('a', 'b')",
            name=op.f("ck_build_plate_surfaces_build_plate_surface_side"),
        ),
        sa.CheckConstraint(
            "surface_code ~ '^P[1-9][0-9]*b?$'",
            name=op.f("ck_build_plate_surfaces_build_plate_surface_code_format"),
        ),
        sa.CheckConstraint(
            "klipper_mesh_profile = surface_code",
            name=op.f("ck_build_plate_surfaces_build_plate_surface_mesh_matches_code"),
        ),
        sa.ForeignKeyConstraint(
            ["build_plate_id"],
            ["build_plates.id"],
            name=op.f("fk_build_plate_surfaces_build_plate_id_build_plates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_build_plate_surfaces")),
        sa.UniqueConstraint(
            "build_plate_id",
            "side",
            name="uq_build_plate_surface_side",
        ),
        sa.UniqueConstraint(
            "surface_code",
            name=op.f("uq_build_plate_surfaces_surface_code"),
        ),
        sa.UniqueConstraint(
            "klipper_mesh_profile",
            name=op.f("uq_build_plate_surfaces_klipper_mesh_profile"),
        ),
    )
    op.create_index(
        op.f("ix_build_plate_surfaces_build_plate_id"),
        "build_plate_surfaces",
        ["build_plate_id"],
        unique=False,
    )

    plates = connection.execute(
        sa.text(
            """
            SELECT id, plate_code, klipper_mesh_profile, surface_type,
                   last_mesh_calibrated_at, record_version
            FROM build_plates
            """
        )
    ).mappings()
    surface_table = sa.table(
        "build_plate_surfaces",
        sa.column("build_plate_id", sa.UUID()),
        sa.column("side", sa.String()),
        sa.column("surface_code", sa.String()),
        sa.column("klipper_mesh_profile", sa.String()),
        sa.column("surface_material", sa.String()),
        sa.column("last_mesh_calibrated_at", sa.DateTime(timezone=True)),
        sa.column("record_version", sa.Integer()),
        sa.column("id", sa.UUID()),
    )
    side_a_rows = [
        {
            "build_plate_id": plate["id"],
            "side": "a",
            "surface_code": plate["plate_code"],
            "klipper_mesh_profile": plate["klipper_mesh_profile"],
            "surface_material": plate["surface_type"],
            "last_mesh_calibrated_at": plate["last_mesh_calibrated_at"],
            "record_version": plate["record_version"],
            "id": uuid4(),
        }
        for plate in plates
    ]
    if side_a_rows:
        op.bulk_insert(surface_table, side_a_rows)

    op.add_column("printers", sa.Column("active_plate_surface_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_printers_active_plate_surface_id_build_plate_surfaces"),
        "printers",
        "build_plate_surfaces",
        ["active_plate_surface_id"],
        ["id"],
    )
    connection.execute(
        sa.text(
            """
            UPDATE printers AS printer
            SET active_plate_surface_id = surface.id
            FROM build_plate_surfaces AS surface
            WHERE surface.build_plate_id = printer.active_plate_id AND surface.side = 'a'
            """
        )
    )

    op.add_column(
        "calibration_sessions",
        sa.Column("build_plate_surface_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_calibration_sessions_build_plate_surface_id_build_plate_surfaces"),
        "calibration_sessions",
        "build_plate_surfaces",
        ["build_plate_surface_id"],
        ["id"],
    )
    connection.execute(
        sa.text(
            """
            UPDATE calibration_sessions AS calibration
            SET build_plate_surface_id = surface.id
            FROM build_plate_surfaces AS surface
            WHERE surface.build_plate_id = calibration.build_plate_id AND surface.side = 'a'
            """
        )
    )

    op.add_column(
        "material_profiles",
        sa.Column("preferred_build_plate_surface_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_material_profiles_preferred_build_plate_surface_id_build_plate_surfaces"),
        "material_profiles",
        "build_plate_surfaces",
        ["preferred_build_plate_surface_id"],
        ["id"],
    )
    connection.execute(
        sa.text(
            """
            UPDATE material_profiles AS profile
            SET preferred_build_plate_surface_id = surface.id
            FROM build_plate_surfaces AS surface
            WHERE surface.build_plate_id = profile.preferred_build_plate_id AND surface.side = 'a'
            """
        )
    )
    op.drop_constraint(
        op.f("fk_material_profiles_preferred_build_plate_id_build_plates"),
        "material_profiles",
        type_="foreignkey",
    )
    op.drop_column("material_profiles", "preferred_build_plate_id")

    op.drop_column("build_plates", "last_mesh_calibrated_at")
    op.drop_column("build_plates", "surface_type")
    op.drop_column("build_plates", "klipper_mesh_profile")
    op.add_column(
        "workstation_agents",
        sa.Column(
            "cura_materials",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("workstation_agents", "cura_materials", server_default=None)


def downgrade() -> None:
    """Collapse each plate back to Side A without silently losing extended IDs."""

    connection = op.get_bind()
    extended_code = connection.execute(
        sa.text("SELECT plate_code FROM build_plates WHERE length(plate_code) > 2 LIMIT 1")
    ).scalar_one_or_none()
    if extended_code is not None:
        raise RuntimeError(
            "Cannot downgrade while build plates beyond P9 exist; remove or rename them explicitly first"
        )

    op.drop_column("workstation_agents", "cura_materials")

    op.drop_constraint(
        op.f("fk_calibration_sessions_build_plate_surface_id_build_plate_surfaces"),
        "calibration_sessions",
        type_="foreignkey",
    )
    op.drop_column("calibration_sessions", "build_plate_surface_id")

    op.add_column(
        "build_plates",
        sa.Column("klipper_mesh_profile", sa.String(length=120), nullable=True),
    )
    op.add_column("build_plates", sa.Column("surface_type", sa.String(length=120), nullable=True))
    op.add_column(
        "build_plates",
        sa.Column("last_mesh_calibrated_at", sa.DateTime(timezone=True), nullable=True),
    )
    connection.execute(
        sa.text(
            """
            UPDATE build_plates AS plate
            SET klipper_mesh_profile = surface.klipper_mesh_profile,
                surface_type = surface.surface_material,
                last_mesh_calibrated_at = surface.last_mesh_calibrated_at
            FROM build_plate_surfaces AS surface
            WHERE surface.build_plate_id = plate.id AND surface.side = 'a'
            """
        )
    )
    op.alter_column(
        "build_plates",
        "klipper_mesh_profile",
        existing_type=sa.String(length=120),
        nullable=False,
    )

    op.add_column(
        "material_profiles",
        sa.Column("preferred_build_plate_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_material_profiles_preferred_build_plate_id_build_plates"),
        "material_profiles",
        "build_plates",
        ["preferred_build_plate_id"],
        ["id"],
    )
    connection.execute(
        sa.text(
            """
            UPDATE material_profiles AS profile
            SET preferred_build_plate_id = surface.build_plate_id
            FROM build_plate_surfaces AS surface
            WHERE surface.id = profile.preferred_build_plate_surface_id
            """
        )
    )
    op.drop_constraint(
        op.f("fk_material_profiles_preferred_build_plate_surface_id_build_plate_surfaces"),
        "material_profiles",
        type_="foreignkey",
    )
    op.drop_column("material_profiles", "preferred_build_plate_surface_id")

    op.drop_constraint(
        op.f("fk_printers_active_plate_surface_id_build_plate_surfaces"),
        "printers",
        type_="foreignkey",
    )
    op.drop_column("printers", "active_plate_surface_id")
    op.drop_index(
        op.f("ix_build_plate_surfaces_build_plate_id"),
        table_name="build_plate_surfaces",
    )
    op.drop_table("build_plate_surfaces")
    postgresql.ENUM(name="plate_surface_texture").drop(connection, checkfirst=True)

    op.drop_column("build_plates", "description")
    op.drop_constraint(
        op.f("ck_build_plates_build_plate_code_format"),
        "build_plates",
        type_="check",
    )
    op.alter_column(
        "build_plates",
        "plate_code",
        existing_type=sa.String(length=32),
        type_=sa.String(length=2),
        existing_nullable=False,
    )
