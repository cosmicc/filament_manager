"""Directly save edits to known managed Cura materials."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.api.schemas import CuraManagedMaterialReport, MaterialSettingsInput
from filament_manager.domain.cura_import import cura_setting_maps_equal, material_settings_from_cura
from filament_manager.domain.cura_material_settings import (
    CURA_EDITABLE_SETTING_KEYS,
    CURA_TEMPLATE_ONLY_SETTING_KEYS,
)
from filament_manager.domain.profile_inheritance import resolve_profile_settings
from filament_manager.domain.spool_preflight import (
    cura_material_guid,
    cura_product_material_guid,
)
from filament_manager.models.enums import ProfileStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
)
from filament_manager.models.workstations import CuraManagedEditReceipt, WorkstationAgent
from filament_manager.services.cura_library import settings_from_template
from filament_manager.services.events import add_audit_event
from filament_manager.services.material_settings import (
    create_published_profile_snapshot,
    save_template_settings,
)

MAX_GUID_LOOKUP_REVISIONS = 10_000


def merge_editable_cura_settings(
    expected: Mapping[str, object],
    reported: Mapping[str, str | bool],
    *,
    source_kind: str,
) -> dict[str, object]:
    """Apply only controls that the selected managed material is allowed to own."""

    allowed = set(CURA_EDITABLE_SETTING_KEYS)
    if source_kind == "product":
        allowed.difference_update(CURA_TEMPLATE_ONLY_SETTING_KEYS)
    merged = dict(expected)
    for key in allowed.intersection(reported):
        merged[key] = reported[key]
    return merged


async def _source_by_guid(
    session: AsyncSession,
    material_guid: UUID,
) -> tuple[str, MaterialProfile | MaterialTemplateRevision] | None:
    """Resolve one deterministic managed GUID against bounded published history."""

    expected = str(material_guid)
    profiles = list(
        await session.scalars(
            select(MaterialProfile)
            .where(MaterialProfile.status == ProfileStatus.PUBLISHED)
            .order_by(MaterialProfile.published_at.desc())
            .limit(MAX_GUID_LOOKUP_REVISIONS)
        )
    )
    for profile in profiles:
        if expected in {
            cura_material_guid("product", profile.id),
            cura_product_material_guid(
                profile.filament_product_id,
                profile.printer_id,
                profile.nozzle_diameter_mm,
            ),
        }:
            return "product", profile
    revisions = list(
        await session.scalars(
            select(MaterialTemplateRevision)
            .where(MaterialTemplateRevision.status == ProfileStatus.PUBLISHED)
            .order_by(MaterialTemplateRevision.published_at.desc())
            .limit(MAX_GUID_LOOKUP_REVISIONS)
        )
    )
    for revision in revisions:
        if cura_material_guid("template", revision.id) == expected:
            return "template", revision
        template = await session.get(MaterialTemplate, revision.material_template_id)
        if template is not None and cura_material_guid("template", template.id) == expected:
            return "template", revision
    return None


async def _receipt_exists(
    session: AsyncSession,
    *,
    material_guid: UUID,
    content_checksum: str,
) -> bool:
    """Deduplicate the same semantic edit across every managed workstation."""

    return (
        await session.scalar(
            select(CuraManagedEditReceipt.id).where(
                CuraManagedEditReceipt.material_guid == str(material_guid),
                CuraManagedEditReceipt.content_checksum == content_checksum,
            )
        )
        is not None
    )


def _content_checksum(report: CuraManagedMaterialReport) -> str:
    """Derive edit identity from validated content instead of trusting agent metadata."""

    content = {
        "material_guid": str(report.material_guid),
        "settings": dict(report.settings),
    }
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


async def import_managed_cura_edits(
    session: AsyncSession,
    *,
    agent: WorkstationAgent,
    reports: list[CuraManagedMaterialReport],
    correlation_id: str,
) -> int:
    """Directly save each idempotent semantic change to a known material."""

    imported = 0
    for report in reports:
        content_checksum = _content_checksum(report)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:edit_key, 0))"),
            {"edit_key": f"cura-edit:{report.material_guid}:{content_checksum}"},
        )
        if await _receipt_exists(
            session,
            material_guid=report.material_guid,
            content_checksum=content_checksum,
        ):
            continue
        source = await _source_by_guid(session, report.material_guid)
        if source is None:
            # Unknown GUIDs are not creation requests. Authoritative deployment
            # removes them without admitting untrusted new canonical objects.
            continue
        source_kind, source_revision = source
        created_profile_id: UUID | None = None
        created_template_id: UUID | None = None

        if source_kind == "product":
            assert isinstance(source_revision, MaterialProfile)
            product = await session.get(FilamentProduct, source_revision.filament_product_id)
            base_revision = (
                await session.get(MaterialTemplateRevision, source_revision.base_template_revision_id)
                if source_revision.base_template_revision_id
                else None
            )
            if product is None or base_revision is None:
                continue
            expected_cura = settings_from_template(
                resolve_profile_settings(
                    base_revision.settings,
                    dict(source_revision.setting_overrides or {}),
                )
            )
            incoming_cura = merge_editable_cura_settings(
                expected_cura,
                report.settings,
                source_kind=source_kind,
            )
            if cura_setting_maps_equal(expected_cura, incoming_cura):
                continue
            product_settings = MaterialSettingsInput.model_validate(
                material_settings_from_cura(
                    incoming_cura,
                    filament_density_g_cm3=product.density_g_cm3,
                    preferred_build_plate_surface_id=source_revision.preferred_build_plate_surface_id,
                )
            ).model_dump(mode="json")
            profile = await create_published_profile_snapshot(
                session,
                filament_product_id=source_revision.filament_product_id,
                printer_id=source_revision.printer_id,
                nozzle_diameter_mm=source_revision.nozzle_diameter_mm,
                base_revision=base_revision,
                settings=product_settings,
            )
            created_profile_id = profile.id
            add_audit_event(
                session,
                actor_id=None,
                source="workstation_agent",
                action="profile.settings.import_cura_edit",
                object_type="material_profile",
                object_id=profile.id,
                before={"source_profile_id": str(source_revision.id)},
                after={
                    "status": "published",
                    "version": profile.version,
                    "workstation_agent_id": str(agent.id),
                    "direct_save": True,
                },
                correlation_id=correlation_id,
            )
        else:
            assert isinstance(source_revision, MaterialTemplateRevision)
            expected_cura = settings_from_template(source_revision.settings)
            incoming_cura = merge_editable_cura_settings(
                expected_cura,
                report.settings,
                source_kind=source_kind,
            )
            if cura_setting_maps_equal(expected_cura, incoming_cura):
                continue
            source_settings = MaterialSettingsInput.model_validate(source_revision.settings)
            template_settings = MaterialSettingsInput.model_validate(
                material_settings_from_cura(
                    incoming_cura,
                    filament_density_g_cm3=source_settings.filament_density_g_cm3,
                    preferred_build_plate_surface_id=source_settings.preferred_build_plate_surface_id,
                )
            )
            template = await session.get(
                MaterialTemplate,
                source_revision.material_template_id,
            )
            if template is None:
                continue
            revision, inherited_profiles = await save_template_settings(
                session,
                template=template,
                settings=template_settings.model_dump(mode="json"),
            )
            created_template_id = revision.id
            add_audit_event(
                session,
                actor_id=None,
                source="workstation_agent",
                action="material_template.settings.import_cura_edit",
                object_type="material_template_revision",
                object_id=revision.id,
                before={"source_revision_id": str(source_revision.id)},
                after={
                    "status": "published",
                    "version": revision.version,
                    "workstation_agent_id": str(agent.id),
                    "linked_profiles_updated": len(inherited_profiles),
                    "direct_save": True,
                },
                correlation_id=correlation_id,
            )

        session.add(
            CuraManagedEditReceipt(
                agent_id=agent.id,
                installation_id=report.installation_id,
                material_guid=str(report.material_guid),
                source_kind=source_kind,
                source_revision_id=source_revision.id,
                content_checksum=content_checksum,
                created_profile_revision_id=created_profile_id,
                created_template_revision_id=created_template_id,
                detected_at=datetime.now(UTC),
            )
        )
        imported += 1
    return imported
