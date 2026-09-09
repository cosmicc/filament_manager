"""Physical spool designs and cached Moonraker duration totals.

Revision ID: fa012b3c4d56
Revises: e9f012a3b4c5
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "fa012b3c4d56"
down_revision = "e9f012a3b4c5"
branch_labels = None
depends_on = None

# Frozen 0.8.1 checksum contract: migration history must not import live schemas.
SETTING_KEYS = """moisture_sensitivity drying_time_hours drying_temp_c chamber_temp_c extruder_temp_c
bed_temp_c initial_bed_temp_c flow_percent print_speed_mm_s outer_wall_speed_mm_s inner_wall_speed_mm_s
infill_speed_mm_s top_bottom_speed_mm_s initial_layer_speed_mm_s travel_speed_mm_s support_speed_mm_s
retraction_distance_mm retraction_speed_mm_s retraction_prime_speed_mm_s cooling_enabled cooling_min_percent
cooling_max_percent support_overhang_angle_deg tree_max_branch_angle_deg pressure_advance ironing_flow_percent
ironing_speed_mm_s ironing_line_spacing_mm filament_density_g_cm3 preferred_build_plate_surface_id cura_extensions""".split()
RETIRED_KEYS = set(
    """infill_material_flow ironing_speed default_material_bed_temperature
default_material_print_temperature material_final_print_temperature material_flow_layer_0
material_initial_print_temperature material_print_temperature_layer_0 material_standby_temperature
limit_support_retractions ironing_enabled roofing_material_flow skirt_brim_material_flow support_material_flow""".split()
)


def _inherit_density() -> None:
    """Append corrected current snapshots; preserve every referenced historical row."""
    connection = op.get_bind()
    metadata = sa.MetaData()
    profiles = sa.Table("material_profiles", metadata, autoload_with=connection)
    revisions = sa.Table("material_template_revisions", metadata, autoload_with=connection)
    outbox = sa.Table("outbox_jobs", metadata, autoload_with=connection)
    audits = sa.Table("audit_events", metadata, autoload_with=connection)
    current = (
        connection.execute(
            sa.select(profiles)
            .distinct(profiles.c.filament_product_id, profiles.c.printer_id, profiles.c.nozzle_diameter_mm)
            .order_by(
                profiles.c.filament_product_id,
                profiles.c.printer_id,
                profiles.c.nozzle_diameter_mm,
                profiles.c.version.desc(),
            )
        )
        .mappings()
        .all()
    )
    now = datetime.now(UTC)
    for source in current:
        if source["status"] != "PUBLISHED":
            continue
        base = connection.scalar(
            sa.select(revisions.c.settings).where(revisions.c.id == source["source_template_revision_id"])
        )
        if not isinstance(base, dict) or base.get("filament_density_g_cm3") is None:
            raise RuntimeError(
                "A current profile has no template density; repair its template before upgrading."
            )
        density = Decimal(str(base["filament_density_g_cm3"])).quantize(Decimal("0.00001"))
        overrides = dict(source["setting_overrides"] or {})
        if source["filament_density_g_cm3"] == density and "filament_density_g_cm3" not in overrides:
            continue
        overrides.pop("filament_density_g_cm3", None)
        values = dict(source)
        identity = uuid4()
        values.update(
            id=identity,
            version=source["version"] + 1,
            filament_density_g_cm3=density,
            setting_overrides=overrides,
            source_workstation_agent_id=None,
            source_cura_material_id=None,
            published_at=now,
            created_at=now,
            updated_at=now,
            record_version=1,
        )
        settings = {key: values[key] for key in SETTING_KEYS}
        # Match the frozen validation-time checksum defaults without altering
        # unrelated stored settings or historical snapshots.
        extensions = {
            key: value for key, value in (values["cura_extensions"] or {}).items() if key not in RETIRED_KEYS
        }
        extensions.setdefault("cool_fan_speed_0", "0")
        settings["cura_extensions"] = extensions
        payload = {
            "profile_id": str(identity),
            "version": values["version"],
            "filament_product_id": str(values["filament_product_id"]),
            "printer_id": str(values["printer_id"]),
            "nozzle_diameter_mm": format(values["nozzle_diameter_mm"], "f"),
            "base_template_revision_id": str(values["source_template_revision_id"]),
            "setting_overrides": overrides,
            "settings": settings,
        }

        def scalar(value: object) -> str:
            if isinstance(value, Decimal | UUID):
                return str(value)
            raise TypeError("Unsupported snapshot scalar")

        values["checksum"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=scalar).encode()
        ).hexdigest()
        connection.execute(profiles.insert().values(**values))
        connection.execute(
            audits.insert().values(
                id=uuid4(),
                actor_id=None,
                source="migration",
                action="profile.inherit_template_density",
                object_type="material_profile",
                object_id=identity,
                before={
                    "profile_id": str(source["id"]),
                    "filament_density_g_cm3": str(source["filament_density_g_cm3"]),
                },
                after={"profile_id": str(identity), "filament_density_g_cm3": str(density)},
                metadata={},
                correlation_id="migration-0.8.1-density",
                occurred_at=now,
            )
        )
        connection.execute(
            outbox.insert().values(
                id=uuid4(),
                job_type="google.profile.publish",
                idempotency_key=f"profile:{identity}:google:v1",
                aggregate_type="material_profile",
                aggregate_id=identity,
                aggregate_version=1,
                payload={"profile_id": str(identity)},
                status="PENDING",
                attempts=0,
                max_attempts=12,
                next_attempt_at=now,
                created_at=now,
            )
        )
    # Creation metadata mirrors density for physical mass conversions. Exact
    # per-printer profiles retain their own linked template, including history.
    connection.execute(
        sa.text("""UPDATE filament_products p SET
        density_g_cm3 = (r.settings->>'filament_density_g_cm3')::numeric,
        record_version = p.record_version + 1, updated_at = CURRENT_TIMESTAMP
        FROM material_template_revisions r WHERE r.id = p.source_template_revision_id
        AND r.settings->>'filament_density_g_cm3' IS NOT NULL
        AND p.density_g_cm3 IS DISTINCT FROM (r.settings->>'filament_density_g_cm3')::numeric""")
    )
    connection.execute(
        postgresql.insert(outbox)
        .values(
            id=uuid4(),
            job_type="spoolman.reconcile.full",
            idempotency_key="upgrade:0.8.1:spool-design-density",
            aggregate_type="system",
            aggregate_id=UUID(int=0),
            aggregate_version=1,
            payload={},
            status="PENDING",
            attempts=0,
            max_attempts=12,
            next_attempt_at=now,
            created_at=now,
        )
        .on_conflict_do_nothing()
    )


def upgrade() -> None:
    """Do not guess the design of existing spools or historical printer totals."""
    op.create_table(
        "spool_type_choices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("name_key", sa.String(320), nullable=False, unique=True),
    )
    op.add_column("spools", sa.Column("spool_type", sa.String(160), nullable=False, server_default="Unknown"))
    op.add_column("printers", sa.Column("total_print_time_seconds", sa.Numeric(18, 3)))
    op.add_column("printers", sa.Column("longest_print_time_seconds", sa.Numeric(18, 3)))
    op.add_column("printers", sa.Column("history_totals_checked_at", sa.DateTime(timezone=True)))
    _inherit_density()


def downgrade() -> None:
    """Require a backup rather than silently discarding operator classifications."""
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM spools WHERE spool_type <> 'Unknown') OR EXISTS (SELECT 1 FROM spool_type_choices)"
        )
    ):
        raise RuntimeError("Spool types would be lost; restore a pre-upgrade backup instead.")
    op.drop_column("printers", "history_totals_checked_at")
    op.drop_column("printers", "longest_print_time_seconds")
    op.drop_column("printers", "total_print_time_seconds")
    op.drop_column("spools", "spool_type")
    op.drop_table("spool_type_choices")
