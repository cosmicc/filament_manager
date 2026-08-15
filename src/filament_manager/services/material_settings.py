"""Direct-save material settings with immutable internal snapshots.

The web application presents one current template and one current material
profile per scope.  Each save still appends an immutable published snapshot so
print history, audit records, rollback backups, and outbound synchronization
remain exact without exposing a draft/publish workflow to operators.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.api.schemas import MaterialSettingsInput
from filament_manager.domain.profile_inheritance import (
    profile_columns_from_settings,
    resolve_profile_settings,
    sparse_profile_overrides,
)
from filament_manager.models.enums import ProfileStatus
from filament_manager.models.inventory import (
    FilamentProduct,
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
)
from filament_manager.models.workstations import WorkstationAgent
from filament_manager.services.cura_library import queue_cura_library
from filament_manager.services.events import add_outbox_job


def _checksum(payload: dict[str, object]) -> str:
    """Return one stable SHA-256 identity for a validated JSON snapshot."""

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def template_snapshot_checksum(
    *,
    template_id: UUID,
    version: int,
    settings: dict[str, object],
) -> str:
    """Hash one immutable template settings snapshot."""

    return _checksum(
        {
            "material_template_id": str(template_id),
            "version": version,
            "settings": settings,
        }
    )


def profile_snapshot_checksum(profile: MaterialProfile) -> str:
    """Hash the complete resolved and inherited state of one profile snapshot."""

    settings = MaterialSettingsInput.model_validate(profile).model_dump(mode="json")
    return _checksum(
        {
            "profile_id": str(profile.id),
            "version": profile.version,
            "filament_product_id": str(profile.filament_product_id),
            "printer_id": str(profile.printer_id),
            "nozzle_diameter_mm": format(profile.nozzle_diameter_mm, "f"),
            "base_template_revision_id": str(profile.base_template_revision_id),
            "setting_overrides": profile.setting_overrides,
            "settings": settings,
        }
    )


async def create_published_profile_snapshot(
    session: AsyncSession,
    *,
    filament_product_id: UUID,
    printer_id: UUID,
    nozzle_diameter_mm: Decimal,
    base_revision: MaterialTemplateRevision,
    settings: dict[str, object],
    setting_overrides: dict[str, object] | None = None,
) -> MaterialProfile:
    """Append and finalize one current material-profile snapshot."""

    validated = MaterialSettingsInput.model_validate(settings).model_dump(mode="json")
    latest_version = await session.scalar(
        select(func.max(MaterialProfile.version)).where(
            MaterialProfile.filament_product_id == filament_product_id,
            MaterialProfile.printer_id == printer_id,
            MaterialProfile.nozzle_diameter_mm == nozzle_diameter_mm,
        )
    )
    profile = MaterialProfile(
        **profile_columns_from_settings(validated),
        filament_product_id=filament_product_id,
        printer_id=printer_id,
        nozzle_diameter_mm=nozzle_diameter_mm,
        version=(latest_version or 0) + 1,
        status=ProfileStatus.PUBLISHED,
        base_template_revision_id=base_revision.id,
        setting_overrides=(
            dict(setting_overrides)
            if setting_overrides is not None
            else sparse_profile_overrides(base_revision.settings, validated)
        ),
        published_at=datetime.now(UTC),
    )
    session.add(profile)
    await session.flush()
    profile.checksum = profile_snapshot_checksum(profile)
    add_outbox_job(
        session,
        job_type="google.profile.publish",
        idempotency_key=f"profile:{profile.id}:google:v1",
        aggregate_type="material_profile",
        aggregate_id=profile.id,
        aggregate_version=1,
        payload={"profile_id": str(profile.id)},
    )
    return profile


async def save_template_settings(
    session: AsyncSession,
    *,
    template: MaterialTemplate,
    settings: dict[str, object],
    increment_template_record: bool = True,
) -> tuple[MaterialTemplateRevision, list[MaterialProfile]]:
    """Save a template and immediately update every linked current profile.

    Existing sparse overrides are copied exactly.  This preserves explicit
    ownership even when a customized value happens to equal the new template
    value, so a later template edit cannot silently take control of it.
    """

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:template_key, 0))"),
        {"template_key": f"material-template:{template.id}"},
    )
    validated = MaterialSettingsInput.model_validate(settings).model_dump(mode="json")
    latest_version = await session.scalar(
        select(func.max(MaterialTemplateRevision.version)).where(
            MaterialTemplateRevision.material_template_id == template.id
        )
    )
    version = (latest_version or 0) + 1
    revision = MaterialTemplateRevision(
        material_template_id=template.id,
        version=version,
        status=ProfileStatus.PUBLISHED,
        settings=validated,
        checksum=template_snapshot_checksum(
            template_id=template.id,
            version=version,
            settings=validated,
        ),
        published_at=datetime.now(UTC),
    )
    session.add(revision)
    if increment_template_record:
        template.record_version += 1
    await session.flush()

    template_revision_ids = list(
        await session.scalars(
            select(MaterialTemplateRevision.id).where(
                MaterialTemplateRevision.material_template_id == template.id
            )
        )
    )
    products = list(
        await session.scalars(
            select(FilamentProduct)
            .where(FilamentProduct.source_template_revision_id.in_(template_revision_ids))
            .with_for_update()
        )
    )
    product_ids = {product.id for product in products}
    for product in products:
        if product.source_template_revision_id != revision.id:
            product.source_template_revision_id = revision.id
            product.record_version += 1

    if not product_ids:
        return revision, []

    historical_profiles = list(
        await session.scalars(
            select(MaterialProfile)
            .where(
                MaterialProfile.filament_product_id.in_(product_ids),
                MaterialProfile.printer_id == template.printer_id,
                MaterialProfile.nozzle_diameter_mm == template.nozzle_diameter_mm,
            )
            .order_by(
                MaterialProfile.filament_product_id,
                MaterialProfile.version.desc(),
            )
        )
    )
    current_profiles: dict[UUID, MaterialProfile] = {}
    for profile in historical_profiles:
        current_profiles.setdefault(profile.filament_product_id, profile)

    inherited_profiles: list[MaterialProfile] = []
    for source in current_profiles.values():
        overrides = dict(source.setting_overrides or {})
        effective_settings = resolve_profile_settings(validated, overrides)
        inherited_profiles.append(
            await create_published_profile_snapshot(
                session,
                filament_product_id=source.filament_product_id,
                printer_id=source.printer_id,
                nozzle_diameter_mm=source.nozzle_diameter_mm,
                base_revision=revision,
                settings=effective_settings,
                setting_overrides=overrides,
            )
        )
    return revision, inherited_profiles


async def queue_managed_cura_library(
    session: AsyncSession,
    *,
    requested_by: UUID | None,
) -> int:
    """Queue the current desired library for every enabled managed workstation."""

    agents = list(
        await session.scalars(
            select(WorkstationAgent).where(
                WorkstationAgent.enabled.is_(True),
                WorkstationAgent.cura_management_enabled.is_(True),
            )
        )
    )
    if not agents:
        return 0
    deployments = await queue_cura_library(
        session,
        agents,
        requested_by=requested_by,
        force=True,
    )
    return len(deployments)
