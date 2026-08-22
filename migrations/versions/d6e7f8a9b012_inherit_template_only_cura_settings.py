"""normalize Cura ownership and recover projection retries

Revision ID: d6e7f8a9b012
Revises: c5d6e7f8a901
Create Date: 2026-08-21
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b012"
down_revision: str | None = "c5d6e7f8a901"
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
    "retraction_prime_speed_mm_s",
    "cooling_enabled",
    "cooling_min_percent",
    "cooling_max_percent",
    "support_overhang_angle_deg",
    "tree_max_branch_angle_deg",
    "pressure_advance",
    "ironing_enabled",
    "ironing_flow_percent",
    "ironing_speed_mm_s",
    "ironing_line_spacing_mm",
    "filament_density_g_cm3",
    "preferred_build_plate_surface_id",
)
TEMPLATE_ONLY_EXTENSION_KEYS = frozenset(
    {
        "acceleration_infill",
        "acceleration_print",
        "acceleration_roofing",
        "acceleration_support",
        "acceleration_topbottom",
        "acceleration_travel",
        "acceleration_wall",
        "klipper_smooth_time_enable",
        "klipper_smooth_time_factor",
        "cool_fan_full_layer",
        "cool_min_layer_time",
        "cool_min_layer_time_fan_speed_max",
        "cool_min_speed",
        "skirt_brim_speed",
        "speed_roofing",
        "speed_travel_layer_0",
        "speed_wall",
    }
)
TEMPLATE_ONLY_PROFILE_KEYS = frozenset(
    {
        "print_speed_mm_s",
        "outer_wall_speed_mm_s",
        "inner_wall_speed_mm_s",
        "infill_speed_mm_s",
        "top_bottom_speed_mm_s",
        "initial_layer_speed_mm_s",
        "travel_speed_mm_s",
        "support_speed_mm_s",
        "cooling_enabled",
        "cooling_min_percent",
        "cooling_max_percent",
    }
)
RETIRED_EXTENSION_KEYS = frozenset(
    {
        "infill_material_flow",
        "material_bed_temperature_layer_0",
        "material_final_print_temperature",
        "material_flow_layer_0",
        "material_initial_print_temperature",
        "material_print_temperature_layer_0",
        "material_standby_temperature",
        "roofing_material_flow",
        "skirt_brim_material_flow",
        "support_material_flow",
    }
)


def _plain(value: object) -> object:
    """Return the JSON representation used by application snapshot hashes."""

    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    return value


def _filtered_overrides(value: object) -> dict[str, object]:
    """Drop legacy filament ownership of every new template-only setting."""

    overrides = dict(value) if isinstance(value, dict) else {}
    for key in TEMPLATE_ONLY_PROFILE_KEYS:
        overrides.pop(key, None)
    extensions = overrides.pop("cura_extensions", None)
    if isinstance(extensions, dict):
        retained = {
            str(key): item
            for key, item in extensions.items()
            if str(key) not in TEMPLATE_ONLY_EXTENSION_KEYS | RETIRED_EXTENSION_KEYS
        }
        if retained:
            overrides["cura_extensions"] = retained
    return overrides


def _inherited_extensions(current: object, template: object) -> dict[str, object]:
    """Overlay only template-owned extension values onto a resolved snapshot."""

    resolved = {
        str(key): item
        for key, item in (current.items() if isinstance(current, dict) else [])
        if str(key) not in RETIRED_EXTENSION_KEYS
    }
    base = dict(template) if isinstance(template, dict) else {}
    for key in TEMPLATE_ONLY_EXTENSION_KEYS:
        if key in base:
            resolved[key] = base[key]
        else:
            resolved.pop(key, None)
    return resolved


def _profile_checksum(values: dict[str, object]) -> str:
    """Hash one migrated snapshot with the same canonical application envelope."""

    settings = {key: _plain(values.get(key)) for key in PROFILE_SETTING_KEYS}
    settings["cura_extensions"] = dict(values.get("cura_extensions") or {})
    payload = {
        "profile_id": str(values["id"]),
        "version": values["version"],
        "filament_product_id": str(values["filament_product_id"]),
        "printer_id": str(values["printer_id"]),
        "nozzle_diameter_mm": format(values["nozzle_diameter_mm"], "f"),
        "base_template_revision_id": str(values["source_template_revision_id"]),
        "setting_overrides": values["setting_overrides"],
        "settings": settings,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def upgrade() -> None:
    """Append corrected snapshots and make recoverable projection work actionable."""

    connection = op.get_bind()
    metadata = sa.MetaData()
    profiles = sa.Table("material_profiles", metadata, autoload_with=connection)
    revisions = sa.Table("material_template_revisions", metadata, autoload_with=connection)
    outbox = sa.Table("outbox_jobs", metadata, autoload_with=connection)
    # A successful recurring convergence replaces manual as well as scheduler-
    # generated runs of the same reconstructable operation. Retain the rows as
    # history without showing an already-recovered event as queue debt.
    recurring_types = (
        "spoolman.reconcile.full",
        "moonraker.state.reconcile",
        "moonraker.printer_info.reconcile",
        "moonraker.print_history.reconcile",
        "notifications.evaluate",
        "google.publish.pending",
    )
    connection.execute(
        sa.text(
            "UPDATE outbox_jobs AS failed SET status = 'SUPERSEDED'::job_status,"
            " completed_at = COALESCE(failed.completed_at, CURRENT_TIMESTAMP)"
            " WHERE failed.job_type = ANY(:recurring_types)"
            " AND failed.status IN ('FAILED'::job_status, 'DEAD'::job_status)"
            " AND EXISTS ("
            " SELECT 1 FROM outbox_jobs AS recovered"
            " WHERE recovered.job_type = failed.job_type"
            " AND recovered.status = 'COMPLETED'::job_status"
            " AND recovered.completed_at >= COALESCE(failed.last_error_at, failed.created_at)"
            " )"
        ),
        {"recurring_types": list(recurring_types)},
    )
    # v0.3.2 retried net-weight corrections through Spoolman's gross scale
    # endpoint. Keep only the newest desired correction per spool and retry it
    # immediately through the corrected supported remaining-weight update.
    connection.execute(
        sa.text(
            "WITH ranked AS ("
            " SELECT id, row_number() OVER (PARTITION BY aggregate_id ORDER BY created_at DESC, id DESC) AS rn"
            " FROM outbox_jobs"
            " WHERE job_type = 'spoolman.spool.adjust_weight'"
            " AND status IN ('PENDING'::job_status, 'FAILED'::job_status, 'DEAD'::job_status)"
            ") UPDATE outbox_jobs SET status = 'SUPERSEDED'::job_status,"
            " completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)"
            " WHERE id IN (SELECT id FROM ranked WHERE rn > 1)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE outbox_jobs SET status = 'PENDING'::job_status, attempts = 0,"
            " next_attempt_at = CURRENT_TIMESTAMP, locked_by = NULL, locked_at = NULL,"
            " completed_at = NULL, last_error_class = NULL, last_error_message = NULL,"
            " last_error_at = NULL"
            " WHERE job_type = 'spoolman.spool.adjust_weight'"
            " AND status IN ('PENDING'::job_status, 'FAILED'::job_status, 'DEAD'::job_status)"
        )
    )
    latest = (
        sa.select(
            profiles.c.filament_product_id,
            profiles.c.printer_id,
            profiles.c.nozzle_diameter_mm,
            sa.func.max(profiles.c.version).label("version"),
        )
        .where(profiles.c.status == "PUBLISHED")
        .group_by(
            profiles.c.filament_product_id,
            profiles.c.printer_id,
            profiles.c.nozzle_diameter_mm,
        )
        .subquery()
    )
    current_profiles = list(
        connection.execute(
            sa.select(profiles)
            .join(
                latest,
                (profiles.c.filament_product_id == latest.c.filament_product_id)
                & (profiles.c.printer_id == latest.c.printer_id)
                & (profiles.c.nozzle_diameter_mm == latest.c.nozzle_diameter_mm)
                & (profiles.c.version == latest.c.version),
            )
            .order_by(profiles.c.id)
        ).mappings()
    )
    now = datetime.now(UTC)
    for source in current_profiles:
        template_settings = connection.scalar(
            sa.select(revisions.c.settings).where(revisions.c.id == source["source_template_revision_id"])
        )
        if not isinstance(template_settings, dict):
            continue
        template_extensions = template_settings.get("cura_extensions")
        inherited_extensions = _inherited_extensions(
            source["cura_extensions"],
            template_extensions,
        )
        filtered_overrides = _filtered_overrides(source["setting_overrides"])
        inherited_profile_values = {
            key: (
                bool(template_settings.get(key))
                if key == "cooling_enabled"
                else Decimal(str(template_settings[key]))
                if template_settings.get(key) is not None
                else None
            )
            for key in TEMPLATE_ONLY_PROFILE_KEYS
        }
        if (
            all(source[key] == inherited_profile_values[key] for key in TEMPLATE_ONLY_PROFILE_KEYS)
            and dict(source["cura_extensions"] or {}) == inherited_extensions
            and dict(source["setting_overrides"] or {}) == filtered_overrides
        ):
            continue

        values = dict(source)
        profile_id = uuid4()
        values.update(
            {
                "id": profile_id,
                "version": int(source["version"]) + 1,
                **inherited_profile_values,
                "cura_extensions": inherited_extensions,
                "setting_overrides": filtered_overrides,
                "source_workstation_agent_id": None,
                "source_cura_material_id": None,
                "published_at": now,
                "record_version": 1,
                "created_at": now,
                "updated_at": now,
            }
        )
        values["checksum"] = _profile_checksum(values)
        connection.execute(profiles.insert().values(**values))
        connection.execute(
            outbox.insert().values(
                id=uuid4(),
                job_type="google.profile.publish",
                idempotency_key=f"profile:{profile_id}:google:v1",
                aggregate_type="material_profile",
                aggregate_id=profile_id,
                aggregate_version=1,
                payload={"profile_id": str(profile_id)},
                status="PENDING",
                attempts=0,
                max_attempts=12,
                next_attempt_at=now,
                created_at=now,
            )
        )


def downgrade() -> None:
    """Retain appended immutable snapshots when reverting application code."""
