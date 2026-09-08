"""UI-managed encrypted integrations and independent extruder identities.

Revision ID: e9f012a3b4c5
Revises: d8e9f012a3b4
"""

import sqlalchemy as sa
from alembic import op

revision = "e9f012a3b4c5"
down_revision = "d8e9f012a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve legacy environment ownership until explicit UI adoption."""
    op.add_column("google_connection", sa.Column("oauth_client_id", sa.String(512)))
    op.add_column("google_connection", sa.Column("oauth_client_secret", sa.Text()))
    for name, default in (
        ("connection_managed", "false"),
        ("connection_enabled", "true"),
        ("heated_chamber", "false"),
        ("tool_routines_verified", "false"),
    ):
        op.add_column(
            "printers", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text(default))
        )
    op.add_column("printers", sa.Column("encrypted_api_key", sa.Text()))
    op.add_column("printers", sa.Column("max_extruder_temp_c", sa.Numeric(12, 5)))
    op.add_column("printers", sa.Column("max_bed_temp_c", sa.Numeric(12, 5)))
    op.add_column("printers", sa.Column("extruder_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "printers", sa.Column("power_device", sa.String(160), nullable=False, server_default="printer")
    )
    op.add_column("spools", sa.Column("active_extruder", sa.String(32)))
    op.execute("UPDATE spools SET active_extruder = 'extruder' WHERE active_printer_id IS NOT NULL")
    op.create_index(
        "uq_spools_loaded_hotend",
        "spools",
        ["active_printer_id", "active_extruder"],
        unique=True,
        postgresql_where=sa.text("active_printer_id IS NOT NULL AND active_extruder IS NOT NULL"),
    )
    op.execute("""CREATE FUNCTION preserve_spool_code() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.spool_code IS DISTINCT FROM OLD.spool_code THEN
                RAISE EXCEPTION 'Spool codes are immutable';
            END IF;
            RETURN NEW;
        END; $$""")
    op.execute(
        "CREATE TRIGGER spool_code_immutable BEFORE UPDATE OF spool_code ON spools FOR EACH ROW EXECUTE FUNCTION preserve_spool_code()"
    )


def downgrade() -> None:
    """Refuse to discard configured connections or multiple physical identities."""
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM printers WHERE connection_managed OR extruder_count > 1)")
    ).scalar():
        raise RuntimeError(
            "App-managed printers cannot be downgraded safely. Restore a pre-upgrade backup or explicitly migrate these settings first."
        )
    if bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM google_connection WHERE oauth_client_secret IS NOT NULL)")
    ).scalar():
        raise RuntimeError(
            "App-managed Google credentials cannot be downgraded safely. Restore a pre-upgrade backup or explicitly migrate these settings first."
        )
    op.execute("DROP TRIGGER spool_code_immutable ON spools")
    op.execute("DROP FUNCTION preserve_spool_code()")
    op.drop_index("uq_spools_loaded_hotend", table_name="spools")
    op.drop_column("spools", "active_extruder")
    for name in (
        "tool_routines_verified",
        "power_device",
        "extruder_count",
        "max_bed_temp_c",
        "max_extruder_temp_c",
        "heated_chamber",
        "encrypted_api_key",
        "connection_enabled",
        "connection_managed",
    ):
        op.drop_column("printers", name)
    op.drop_column("google_connection", "oauth_client_secret")
    op.drop_column("google_connection", "oauth_client_id")
