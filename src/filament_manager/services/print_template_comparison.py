"""Compare retained print evidence to its original template without rewriting history."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.api.schemas import PrintSettingDifference, PrintTemplateComparison
from filament_manager.domain.cura_material_settings import CURA_EXTENSION_SETTING_KEYS
from filament_manager.domain.filament_care import FILAMENT_CARE_KEYS
from filament_manager.domain.profile_inheritance import PROFILE_SETTING_KEYS, _equivalent
from filament_manager.models.inventory import MaterialTemplate, MaterialTemplateRevision


def compare_print_settings(used: dict[str, object], current: dict[str, object]) -> PrintTemplateComparison:
    """Compare every supported print value, including template-only motion settings.

    Missing historical keys are unknown, not evidence of inheritance. Care metadata
    and raw Cura expressions are intentionally outside this managed-print comparison.
    """

    result = PrintTemplateComparison(status="matches", checked_at=datetime.now(UTC))
    pairs: list[tuple[str, object, object]] = []
    for key in PROFILE_SETTING_KEYS:
        if key in FILAMENT_CARE_KEYS:
            continue
        if key not in used:
            result.missing_keys.append(key)
        else:
            pairs.append((key, used[key], current.get(key)))
    used_extensions = used.get("cura_extensions")
    current_extensions = current.get("cura_extensions")
    if not isinstance(used_extensions, dict):
        result.missing_keys.append("cura_extensions")
    else:
        current_extensions = current_extensions if isinstance(current_extensions, dict) else {}
        for key in sorted((used_extensions.keys() | current_extensions.keys()) & CURA_EXTENSION_SETTING_KEYS):
            pairs.append((f"cura_extensions.{key}", used_extensions.get(key), current_extensions.get(key)))
    for key, before, after in pairs:
        if _equivalent(before, after):
            result.matching_count += 1
        else:
            result.differences.append(PrintSettingDifference(key=key, used=before, current=after))
    result.status = "partial" if result.missing_keys else "differs" if result.differences else "matches"
    return result


async def current_print_template_comparison(
    session: AsyncSession, snapshot: dict[str, object]
) -> PrintTemplateComparison:
    """Read the latest revision of the captured template, not the filament's new link."""

    unavailable = PrintTemplateComparison(status="unavailable", checked_at=datetime.now(UTC))
    managed = snapshot.get("managed")
    if not isinstance(managed, dict):
        return unavailable
    captured_template = managed.get("template")
    used = managed.get("resolved")
    if not isinstance(captured_template, dict) or not isinstance(used, dict) or not used:
        return unavailable
    try:
        template_id = UUID(str(captured_template.get("id")))
    except ValueError:
        return unavailable
    row = (
        await session.execute(
            select(MaterialTemplate, MaterialTemplateRevision)
            .join(
                MaterialTemplateRevision, MaterialTemplateRevision.material_template_id == MaterialTemplate.id
            )
            .where(MaterialTemplate.id == template_id, MaterialTemplate.active.is_(True))
            .order_by(MaterialTemplateRevision.version.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return unavailable
    template, revision = row
    result = compare_print_settings(used, revision.settings)
    result.template_id = template.id
    result.template_name = template.name
    result.template_version = revision.version
    return result
