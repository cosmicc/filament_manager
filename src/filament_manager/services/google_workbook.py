"""Complete, explicitly allowlisted business projection and workbook layout.

Structured settings are flattened into a searchable long-form tab. Values are
inert typed cells, never formulas. Security/connection tables and binary files
are deliberately absent; adding database fields cannot silently export them.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.clients.google_sheets import GoogleSheetsError
from filament_manager.models import Base

# Explicit column contracts also avoid loading ORM relationships or binary data.
EXPORTS = (
    (
        "Spools",
        "spools",
        "spool_code filament_product_id nominal_net_mass_g tare_mass_g "
        "remaining_mass_expected_g remaining_mass_measured_g remaining_mass_effective_g "
        "weight_confidence status purchase_source purchase_date purchase_cost currency "
        "first_used_at last_used_at last_measurement_at last_usage_event_at location "
        "active_printer_id spoolman_id notes archived record_version created_at updated_at",
    ),
    (
        "Filaments",
        "filament_products",
        "material_type color_name filler finish vendor_id color_hex color_mode color_hexes "
        "diameter_mm tolerance_mm density_g_cm3 nominal_net_mass_g notes "
        "source_template_revision_id archived record_version created_at updated_at",
    ),
    (
        "Templates",
        "material_templates",
        "name material_type description printer_id nozzle_id nozzle_diameter_mm "
        "filament_diameter_mm active record_version created_at updated_at",
    ),
    (
        "Template History",
        "material_template_revisions",
        "material_template_id version status settings checksum published_at record_version "
        "created_at updated_at",
    ),
    (
        "Print Profiles",
        "material_profiles",
        "filament_product_id printer_id nozzle_diameter_mm min_layer_height_mm "
        "max_layer_height_mm version status chamber_temp_c drying_temp_c drying_time_hours "
        "moisture_sensitivity extruder_temp_c bed_temp_c initial_bed_temp_c flow_percent "
        "print_speed_mm_s outer_wall_speed_mm_s inner_wall_speed_mm_s infill_speed_mm_s "
        "top_bottom_speed_mm_s initial_layer_speed_mm_s travel_speed_mm_s support_speed_mm_s "
        "bridge_speed_mm_s retraction_distance_mm retraction_speed_mm_s "
        "retraction_prime_speed_mm_s cooling_enabled cooling_min_percent cooling_max_percent "
        "support_overhang_angle_deg tree_max_branch_angle_deg pressure_advance "
        "filament_density_g_cm3 preferred_build_plate_surface_id source_template_revision_id "
        "setting_overrides ironing_flow_percent ironing_speed_mm_s ironing_line_spacing_mm "
        "cura_extensions checksum published_at record_version created_at updated_at",
    ),
    (
        "Build Plates",
        "build_plates",
        "plate_code display_name description manufacturer product_name shape dimensions_mm "
        "magnetic flexible condition status preferred_materials max_bed_temp_c "
        "last_activated_at notes record_version created_at updated_at",
    ),
    (
        "Plate Sides",
        "build_plate_surfaces",
        "build_plate_id side surface_code klipper_mesh_profile surface_material texture "
        "mesh_available last_mesh_calibrated_at last_activated_at last_mesh_observed_at notes "
        "record_version created_at updated_at",
    ),
    (
        "3D Printers",
        "printers",
        "printer_code name nozzle_diameter_mm build_volume manufacturer model kinematics "
        "nozzle_material extruder_type klipper_version moonraker_version notes active_plate_id "
        "active_plate_surface_id active_nozzle_id status record_version created_at updated_at",
    ),
    (
        "Nozzles",
        "nozzles",
        "nozzle_code printer_id diameter_mm material manufacturer product_name coating "
        "purchase_date status installed_at retired_at notes record_version created_at "
        "updated_at",
    ),
    (
        "Nozzle Events",
        "nozzle_lifecycle_events",
        "nozzle_id printer_id event_type source notes occurred_at created_at",
    ),
    (
        "Mesh Calibration",
        "build_plate_maintenance_events",
        "build_plate_id build_plate_surface_id maintenance_type source notes occurred_at created_at",
    ),
    ("Manufacturers", "vendors", "name preferred aliases notes record_version created_at updated_at"),
    ("Locations", "spool_location_choices", "name created_at updated_at"),
    (
        "Colors",
        "filament_colors",
        "name color_hex color_mode color_hexes record_version created_at updated_at",
    ),
    ("Fillers and Finishes", "filament_attribute_choices", "kind name"),
    (
        "Measurements",
        "spool_measurements",
        "spool_id source status gross_mass_g tare_mass_g net_mass_g expected_before_g "
        "variance_g uncertainty_g confidence requires_confirmation confirmed notes "
        "rejection_reason measured_at created_at",
    ),
    (
        "Usage",
        "spool_usage_events",
        "spool_id source printer_id print_job_id mass_delta_g occurred_at created_at",
    ),
    (
        "Calibration",
        "calibration_sessions",
        "filament_product_id spool_id printer_id nozzle_diameter_mm build_plate_id "
        "build_plate_surface_id baseline_profile_id published_profile_id "
        "target_layer_height_mm status notes override_reason started_at completed_at "
        "record_version created_at updated_at",
    ),
    (
        "Calibration Steps",
        "calibration_steps",
        "session_id step_order step_key name required status inputs result artifact "
        "affected_profile_fields notes completed_at record_version created_at updated_at",
    ),
    (
        "Print History",
        "print_jobs",
        "printer_id moonraker_job_id filename gcode_sha256 source status spool_id "
        "filament_product_id material_profile_id material_profile_version build_plate_id "
        "build_plate_surface_id nozzle_id nozzle_diameter_mm material_guid material_name "
        "material_type state_snapshot profile_snapshot print_settings_snapshot "
        "inspection_status inspection_policy inspection inspected_at slicer slicer_version "
        "cura_quality_profile layer_height_mm line_width_mm extruder_temp_c bed_temp_c "
        "initial_bed_temp_c chamber_temp_c print_speed_mm_s pressure_advance "
        "retraction_distance_mm retraction_speed_mm_s flow_percent "
        "predicted_filament_length_mm predicted_filament_weight_g actual_filament_length_mm "
        "actual_filament_weight_g estimated_duration_seconds print_duration_seconds "
        "total_duration_seconds support_configuration machine_name started_at ended_at "
        "record_version created_at updated_at",
    ),
    (
        "Print Segments",
        "print_material_segments",
        "print_job_id segment_number spool_id filament_product_id material_profile_id "
        "material_profile_version source state_snapshot started_at ended_at "
        "actual_filament_length_mm actual_filament_weight_g created_at",
    ),
    (
        "Print Assessments",
        "print_assessments",
        "print_job_id revision rating defect_tags notes supersedes_id created_at",
    ),
)
MAX_CELLS = 2_000_000  # Leave room for the last good and staged generations.
MAX_CONTENT_BYTES = 32 * 1024 * 1024  # Bound worker memory as well as Google's grid size.
SECRET_KEY = re.compile(
    r"password|secret|token|credential|api.?key|authorization|cookie|url|uri$|host|path|directory", re.I
)


@dataclass
class WorkbookTab:
    """One materialized table with stable internal identifiers and typed cells."""

    title: str
    fields: list[str]
    rows: list[list[Any]] = field(default_factory=list)


def scalar(value: Any) -> str | int | float | bool:
    """Preserve literal text and numeric meaning within Google's cell limits."""
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bool, int, float)):
        return value
    result = str(value)
    if len(result) > 45000:
        raise GoogleSheetsError("A workbook value exceeds Google's cell limit. No data was discarded.")
    return result


def flatten(value: Any, path: str = "", depth: int = 0) -> list[tuple[str, Any]]:
    """Keep expressions inert; exclude credential/endpoint-like structured fields."""
    if depth > 24:
        raise GoogleSheetsError("A settings document is too deeply nested to publish safely.")
    if isinstance(value, dict):
        result: list[tuple[str, Any]] = []
        for key, item in sorted(value.items()):
            key_path = f"{path}.{key}" if path else str(key)
            if SECRET_KEY.search(str(key)):
                result.append((key_path, "[excluded: security or connection field]"))
            else:
                result.extend(flatten(item, key_path, depth + 1))
        return result or [(path, "{}")]
    if isinstance(value, list):
        return [
            entry for i, item in enumerate(value) for entry in flatten(item, f"{path}[{i}]", depth + 1)
        ] or [(path, "[]")]
    return [(path, scalar(value))]


async def snapshot(session: AsyncSession) -> list[WorkbookTab]:
    """Read complete tables in one repeatable-read snapshot; never contact a printer."""
    tabs: list[WorkbookTab] = []
    details = WorkbookTab("Settings and Evidence", ["source_tab", "record_id", "field", "setting", "value"])
    cells = 0
    content_bytes = 0
    for title, name, declared in EXPORTS:
        table = Base.metadata.tables[name]
        fields = ["id", *declared.split()]
        tab = WorkbookTab(title, fields)
        # Selecting columns instead of entities prevents relationship N+1 queries.
        records = await session.stream(select(*(table.c[name] for name in fields)).order_by(table.c.id))
        async for record in records:
            row: list[Any] = []
            for name, value in zip(fields, record, strict=True):
                if isinstance(value, (dict, list)):
                    entries = flatten(value)
                    for key, item in entries:
                        detail_row = [title, str(record.id), name, key, item]
                        details.rows.append(detail_row)
                        content_bytes += len(json.dumps(detail_row, ensure_ascii=False).encode())
                    cells += len(entries) * 5
                    row.append(f"{len(entries)} values — Settings and Evidence")
                else:
                    row.append(scalar(value))
            tab.rows.append(row)
            cells += len(fields)
            content_bytes += len(json.dumps(row, ensure_ascii=False).encode())
            if cells > MAX_CELLS or content_bytes > MAX_CONTENT_BYTES:
                raise GoogleSheetsError(
                    "Inventory exceeds the safe workbook size. The last complete publication is retained."
                )
        tabs.append(tab)
    tabs.append(details)
    # Add derived live identities without changing historical captured names.
    filament = next(tab for tab in tabs if tab.title == "Filaments")
    names: dict[str, str] = {}
    for row in filament.rows:
        values = dict(zip(filament.fields, row, strict=True))
        parts = [str(values["material_type"]), str(values["color_name"])]
        parts.extend(
            str(values[key])
            for key in ("filler", "finish")
            if str(values[key]).strip().casefold()
            not in {"", "none", "standard", "not specified", "no filler", "no finish"}
        )
        names[str(values["id"])] = " · ".join(parts)
        row.insert(1, names[str(values["id"])])
    filament.fields.insert(1, "name")
    spools = next(tab for tab in tabs if tab.title == "Spools")
    product_index = spools.fields.index("filament_product_id")
    for row in spools.rows:
        row.insert(1, names.get(str(row[product_index]), "Unknown filament"))
    spools.fields.insert(1, "filament")
    return tabs


def fingerprint(tabs: list[WorkbookTab]) -> str:
    """Hash canonical content, not changing publication timestamps."""
    digest = hashlib.sha256(b"filament-manager-workbook-v1")
    for tab in tabs:
        digest.update(
            json.dumps([tab.title, tab.fields, tab.rows], separators=(",", ":"), ensure_ascii=False).encode()
        )
    return digest.hexdigest()


def cell(value: Any, *, link: str | None = None) -> dict[str, Any]:
    """Explicit stringValue prevents formula injection, including leading '='."""
    kind = (
        "boolValue"
        if isinstance(value, bool)
        else "numberValue"
        if isinstance(value, (int, float))
        else "stringValue"
    )
    result: dict[str, Any] = {"userEnteredValue": {kind: value}}
    if link:
        result["userEnteredFormat"] = {"textFormat": {"link": {"uri": link}}}
    return result
