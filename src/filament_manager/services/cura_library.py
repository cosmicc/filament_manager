"""Build and queue the authoritative desired-state Cura material library."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.domain.cura_material_settings import (
    CURA_EDITABLE_SETTING_KEYS,
    CURA_MANAGED_SETTING_KEYS,
    CURA_RETIRED_SETTING_KEYS,
    CURA_TEMPLATE_ONLY_SETTING_KEYS,
    cura_settings_for_profile,
)
from filament_manager.domain.profile_inheritance import resolve_profile_settings
from filament_manager.domain.spool_preflight import cura_material_guid
from filament_manager.models.enums import CuraDeploymentStatus, ProfileStatus, SpoolStatus
from filament_manager.models.inventory import (
    BuildPlate,
    BuildPlateSurface,
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
    Spool,
    Vendor,
)
from filament_manager.models.workstations import CuraDeployment, WorkstationAgent


def _decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def settings_from_template(snapshot: dict[str, object]) -> dict[str, object]:
    """Convert a validated JSON template snapshot into the Cura setting map."""

    decimal_fields = {
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
        "cooling_min_percent",
        "cooling_max_percent",
        "support_overhang_angle_deg",
        "pressure_advance",
    }
    values = dict(snapshot)
    values.setdefault("retraction_prime_speed_mm_s", values.get("retraction_speed_mm_s"))
    for field in decimal_fields:
        raw = values.get(field)
        values[field] = Decimal(str(raw)) if raw is not None else None
    values.setdefault("cura_extensions", {})
    return cura_settings_for_profile(SimpleNamespace(**values))


async def _plate_payload(session: AsyncSession, surface_id: object | None) -> dict[str, object] | None:
    if surface_id is None:
        return None
    surface = await session.get(BuildPlateSurface, UUID(str(surface_id)))
    plate = await session.get(BuildPlate, surface.build_plate_id) if surface else None
    if surface is None or plate is None:
        return None
    return {
        "code": surface.surface_code,
        "physical_plate_code": plate.plate_code,
        "side": surface.side,
        "name": plate.display_name,
        "surface_material": surface.surface_material,
        "texture": surface.texture.value if surface.texture else None,
    }


async def _printer_payload(
    session: AsyncSession, printer_id: UUID, nozzle_diameter_mm: Decimal
) -> dict[str, object]:
    printer = await session.get(Printer, printer_id)
    if printer is None:
        raise RuntimeError("A Cura library entry references a missing printer")
    return {
        "id": str(printer.id),
        "code": printer.printer_code,
        "name": printer.name,
        "nozzle_diameter_mm": _decimal(nozzle_diameter_mm),
    }


async def _product_cura_costs(session: AsyncSession) -> dict[UUID, dict[str, str]]:
    """Build one currency-safe weighted purchase-cost basis per filament product.

    Cura material profiles identify products rather than physical spools. A normalized
    1,000 g price keeps Cura's estimate mathematically equivalent to the weighted
    cost per gram across currently usable, priced spools without pretending one
    specific physical spool is selected during slicing.
    """

    spools = list(
        await session.scalars(
            select(Spool)
            .where(
                Spool.archived.is_(False),
                Spool.status != SpoolStatus.EMPTY,
                Spool.purchase_cost.is_not(None),
            )
            .order_by(Spool.filament_product_id, Spool.id)
        )
    )
    grouped: dict[UUID, list[Spool]] = {}
    for spool in spools:
        grouped.setdefault(spool.filament_product_id, []).append(spool)

    result: dict[UUID, dict[str, str]] = {}
    for product_id, priced_spools in grouped.items():
        currencies = {spool.currency for spool in priced_spools}
        if len(currencies) != 1:
            # Cura's material-cost preference has no currency field. Mixing
            # currencies would create a plausible-looking but invalid estimate.
            continue
        total_weight = sum((spool.nominal_net_mass_g for spool in priced_spools), Decimal("0"))
        total_cost = sum(
            (spool.purchase_cost or Decimal("0") for spool in priced_spools),
            Decimal("0"),
        )
        if total_weight <= 0:
            continue
        cost_per_gram = total_cost / total_weight
        result[product_id] = {
            "spool_weight_g": "1000",
            "spool_cost": format(
                (cost_per_gram * Decimal("1000")).quantize(Decimal("0.01")),
                "f",
            ),
            "currency": next(iter(currencies)),
            "source_spool_count": str(len(priced_spools)),
        }
    return result


async def build_cura_library(session: AsyncSession) -> dict[str, object]:
    """Return the current templates and product profiles as desired state."""

    entries: list[dict[str, object]] = []
    product_costs = await _product_cura_costs(session)
    templates = list(
        await session.scalars(
            select(MaterialTemplate)
            .where(MaterialTemplate.active.is_(True))
            .order_by(MaterialTemplate.material_type, MaterialTemplate.id)
        )
    )
    for template in templates:
        revisions = list(
            await session.scalars(
                select(MaterialTemplateRevision)
                .where(
                    MaterialTemplateRevision.material_template_id == template.id,
                    MaterialTemplateRevision.status == ProfileStatus.PUBLISHED,
                )
                .order_by(MaterialTemplateRevision.version.desc())
                .limit(1)
            )
        )
        if not revisions:
            continue
        revision = revisions[0]
        entries.append(
            {
                "source_kind": "template",
                "source_id": str(revision.id),
                "cura_material_guid": cura_material_guid("template", revision.id),
                "profile": {
                    "id": str(revision.id),
                    "version": revision.version,
                    "checksum": revision.checksum,
                    "settings": settings_from_template(revision.settings),
                },
                "material": {
                    "product_id": None,
                    "brand": "Template",
                    "material_type": template.material_type,
                    "product_name": f"Template {template.material_type}",
                    "color_name": f"Template {template.material_type}",
                    "filler": None,
                    "finish": None,
                    "color_hex": "#808080",
                    "diameter_mm": _decimal(template.filament_diameter_mm),
                    "density_g_cm3": str(revision.settings["filament_density_g_cm3"]),
                    "nominal_net_mass_g": "1000",
                },
                "printer": await _printer_payload(session, template.printer_id, template.nozzle_diameter_mm),
                "preferred_build_plate": await _plate_payload(
                    session, revision.settings.get("preferred_build_plate_surface_id")
                ),
            }
        )

    profiles = list(
        await session.scalars(
            select(MaterialProfile)
            .where(MaterialProfile.status == ProfileStatus.PUBLISHED)
            .order_by(
                MaterialProfile.filament_product_id,
                MaterialProfile.printer_id,
                MaterialProfile.nozzle_diameter_mm,
                MaterialProfile.version.desc(),
            )
        )
    )
    latest_profiles: dict[tuple[UUID, UUID, Decimal], MaterialProfile] = {}
    for profile in profiles:
        key = (
            profile.filament_product_id,
            profile.printer_id,
            profile.nozzle_diameter_mm,
        )
        latest_profiles.setdefault(key, profile)
    for profile in latest_profiles.values():
        product = await session.get(FilamentProduct, profile.filament_product_id)
        printer = await session.get(Printer, profile.printer_id)
        base_revision = await session.get(
            MaterialTemplateRevision,
            profile.base_template_revision_id,
        )
        if product is None or printer is None or base_revision is None:
            raise RuntimeError("A current material profile has an incomplete scope")
        if product.archived:
            continue
        vendor = await session.get(Vendor, product.vendor_id) if product.vendor_id else None
        effective_settings = resolve_profile_settings(
            base_revision.settings,
            dict(profile.setting_overrides or {}),
        )
        entries.append(
            {
                "source_kind": "product",
                "source_id": str(profile.id),
                "cura_material_guid": cura_material_guid("product", profile.id),
                "profile": {
                    "id": str(profile.id),
                    "version": profile.version,
                    "checksum": profile.checksum,
                    "settings": settings_from_template(effective_settings),
                },
                "material": {
                    "product_id": str(product.id),
                    "brand": vendor.name if vendor else "Unknown",
                    "material_type": product.material_type,
                    "product_name": product.product_name or product.color_name,
                    "color_name": product.color_name,
                    "filler": product.filler,
                    "finish": product.finish,
                    "color_hex": f"#{product.color_hex}" if product.color_hex else "#808080",
                    "diameter_mm": _decimal(product.diameter_mm),
                    "density_g_cm3": _decimal(profile.filament_density_g_cm3),
                    "nominal_net_mass_g": _decimal(product.nominal_net_mass_g),
                    "cura_cost_basis": product_costs.get(product.id),
                },
                "printer": await _printer_payload(session, printer.id, profile.nozzle_diameter_mm),
                "preferred_build_plate": await _plate_payload(
                    session, profile.preferred_build_plate_surface_id
                ),
            }
        )

    entries.sort(key=lambda item: (str(item["source_kind"]), str(item["source_id"])))
    desired_state: dict[str, object] = {
        "schema_version": 3,
        "hide_bundled_materials": True,
        "managed_material_setting_keys": sorted(CURA_MANAGED_SETTING_KEYS),
        "editable_material_setting_keys": sorted(CURA_EDITABLE_SETTING_KEYS),
        "template_only_material_setting_keys": sorted(CURA_TEMPLATE_ONLY_SETTING_KEYS),
        "retired_material_setting_keys": sorted(CURA_RETIRED_SETTING_KEYS),
        "materials": entries,
    }
    checksum = hashlib.sha256(
        json.dumps(desired_state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    desired_state["library_checksum"] = checksum
    return desired_state


async def queue_cura_library(
    session: AsyncSession,
    agents: list[WorkstationAgent],
    *,
    requested_by: UUID | None,
    force: bool = False,
    retry_failed: bool = True,
) -> list[CuraDeployment]:
    """Queue one idempotent full-library deployment per enabled managed workstation."""

    payload = await build_cura_library(session)
    materials = payload["materials"]
    if not isinstance(materials, list) or not materials:
        raise ValueError("Save at least one template or material profile before Cura synchronization")
    checksum = str(payload["library_checksum"])
    now = datetime.now(UTC)
    deployments: list[CuraDeployment] = []
    for agent in agents:
        idempotency_key = f"cura-library:{agent.id}:{checksum}"
        existing = await session.scalar(
            select(CuraDeployment).where(CuraDeployment.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if (retry_failed and existing.status == CuraDeploymentStatus.FAILED) or (
                force
                and existing.status
                in {
                    CuraDeploymentStatus.SUCCEEDED,
                    CuraDeploymentStatus.CANCELLED,
                }
            ):
                existing.status = CuraDeploymentStatus.PENDING
                existing.next_attempt_at = now
                existing.claimed_at = None
                existing.lease_expires_at = None
                existing.completed_at = None
                existing.result = {}
                existing.last_error_class = None
                existing.last_error_message = None
                existing.updated_at = now
            deployments.append(existing)
            continue
        deployment = CuraDeployment(
            agent_id=agent.id,
            material_profile_id=None,
            requested_by=requested_by,
            status=CuraDeploymentStatus.PENDING,
            payload=payload,
            profile_checksum=checksum,
            idempotency_key=idempotency_key,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(deployment)
        deployments.append(deployment)
    await session.flush()
    return deployments
