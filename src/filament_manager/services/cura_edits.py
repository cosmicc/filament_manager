"""Import edits to known managed Cura materials as reviewable draft revisions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.api.schemas import CuraManagedMaterialReport, MaterialSettingsInput
from filament_manager.domain.cura_import import cura_setting_maps_equal, material_settings_from_cura
from filament_manager.domain.cura_material_settings import cura_settings_for_profile
from filament_manager.domain.profile_inheritance import (
    profile_columns_from_settings,
    sparse_profile_overrides,
)
from filament_manager.domain.spool_preflight import cura_material_guid
from filament_manager.models.enums import ProfileStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplateRevision,
)
from filament_manager.models.workstations import CuraManagedEditReceipt, WorkstationAgent
from filament_manager.services.cura_library import settings_from_template
from filament_manager.services.events import add_audit_event

MAX_GUID_LOOKUP_REVISIONS = 10_000


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
        if cura_material_guid("product", profile.id) == expected:
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
    """Create one idempotent draft for each semantically changed known material."""

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
        incoming_cura = dict(report.settings)
        created_profile_id: UUID | None = None
        created_template_id: UUID | None = None

        if source_kind == "product":
            assert isinstance(source_revision, MaterialProfile)
            expected_cura = cura_settings_for_profile(source_revision)
            if cura_setting_maps_equal(expected_cura, incoming_cura):
                continue
            product = await session.get(FilamentProduct, source_revision.filament_product_id)
            base_revision = (
                await session.get(MaterialTemplateRevision, source_revision.base_template_revision_id)
                if source_revision.base_template_revision_id
                else None
            )
            if product is None or base_revision is None:
                continue
            product_settings = MaterialSettingsInput.model_validate(
                material_settings_from_cura(
                    incoming_cura,
                    filament_density_g_cm3=product.density_g_cm3,
                    preferred_build_plate_surface_id=source_revision.preferred_build_plate_surface_id,
                )
            ).model_dump(mode="json")
            latest = await session.scalar(
                select(func.max(MaterialProfile.version)).where(
                    MaterialProfile.filament_product_id == source_revision.filament_product_id,
                    MaterialProfile.printer_id == source_revision.printer_id,
                    MaterialProfile.nozzle_diameter_mm == source_revision.nozzle_diameter_mm,
                )
            )
            profile = MaterialProfile(
                **profile_columns_from_settings(product_settings),
                filament_product_id=source_revision.filament_product_id,
                printer_id=source_revision.printer_id,
                nozzle_diameter_mm=source_revision.nozzle_diameter_mm,
                version=(latest or 0) + 1,
                status=ProfileStatus.DRAFT,
                base_template_revision_id=base_revision.id,
                setting_overrides=sparse_profile_overrides(
                    base_revision.settings,
                    product_settings,
                ),
            )
            session.add(profile)
            await session.flush()
            created_profile_id = profile.id
            add_audit_event(
                session,
                actor_id=None,
                source="workstation_agent",
                action="profile.revision.import_cura_edit",
                object_type="material_profile",
                object_id=profile.id,
                before={"source_profile_id": str(source_revision.id)},
                after={
                    "status": "draft",
                    "version": profile.version,
                    "workstation_agent_id": str(agent.id),
                },
                correlation_id=correlation_id,
            )
        else:
            assert isinstance(source_revision, MaterialTemplateRevision)
            expected_cura = settings_from_template(source_revision.settings)
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
            latest = await session.scalar(
                select(func.max(MaterialTemplateRevision.version)).where(
                    MaterialTemplateRevision.material_template_id == source_revision.material_template_id
                )
            )
            revision = MaterialTemplateRevision(
                material_template_id=source_revision.material_template_id,
                version=(latest or 0) + 1,
                status=ProfileStatus.DRAFT,
                settings=template_settings.model_dump(mode="json"),
            )
            session.add(revision)
            await session.flush()
            created_template_id = revision.id
            add_audit_event(
                session,
                actor_id=None,
                source="workstation_agent",
                action="material_template.revision.import_cura_edit",
                object_type="material_template_revision",
                object_id=revision.id,
                before={"source_revision_id": str(source_revision.id)},
                after={
                    "status": "draft",
                    "version": revision.version,
                    "workstation_agent_id": str(agent.id),
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
