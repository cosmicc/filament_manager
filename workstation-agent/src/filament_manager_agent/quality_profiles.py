"""Validate and sanitize user-owned Cura quality-change profiles."""

import configparser
import io
from dataclasses import dataclass, field
from pathlib import Path

QUALITY_PROFILE_FILE_LIMIT = 1000
QUALITY_PROFILE_MAX_BYTES = 512 * 1024


@dataclass(slots=True)
class QualityProfileCleanupPlan:
    """Bounded file changes required to restore valid material-setting ownership."""

    replacements: dict[Path, bytes] = field(default_factory=dict)
    quarantines: dict[Path, bytes] = field(default_factory=dict)
    removed_setting_count: int = 0
    repaired_profile_count: int = 0


def _parser(*, strict: bool) -> configparser.ConfigParser:
    """Create a non-interpolating parser compatible with Cura instance files."""

    return configparser.ConfigParser(
        interpolation=None,
        strict=strict,
        empty_lines_in_values=False,
    )


def _valid_quality_profile(parser: configparser.ConfigParser) -> bool:
    """Apply Cura's required instance-container metadata checks."""

    if not parser.has_section("general") or not parser.has_section("metadata"):
        return False
    general = parser["general"]
    metadata = parser["metadata"]
    if not str(general.get("name") or "").strip():
        return False
    if not str(general.get("definition") or "").strip():
        return False
    try:
        int(str(general.get("version") or ""))
    except ValueError:
        return False
    return str(metadata.get("type") or "").strip() == "quality_changes"


def _serialize(parser: configparser.ConfigParser) -> bytes:
    """Serialize one repaired profile in Cura's standard INI shape."""

    stream = io.StringIO()
    parser.write(stream)
    return stream.getvalue().encode("utf-8")


def plan_quality_profile_cleanup(
    root: Path,
    managed_setting_keys: frozenset[str],
) -> QualityProfileCleanupPlan:
    """Plan safe rewrites and quarantines without mutating Cura user data."""

    plan = QualityProfileCleanupPlan()
    quality_directory = root / "quality_changes"
    if not quality_directory.is_dir():
        return plan
    paths = sorted(quality_directory.glob("*.cfg"))
    if len(paths) > QUALITY_PROFILE_FILE_LIMIT:
        raise RuntimeError(
            f"Cura has more than {QUALITY_PROFILE_FILE_LIMIT} user quality-profile files; "
            "refusing an unbounded cleanup."
        )
    for path in paths:
        relative = Path("quality_changes") / path.name
        if path.is_symlink():
            raise RuntimeError(f"Refusing to clean symbolic-link Cura profile: {relative}")
        try:
            if path.stat().st_size > QUALITY_PROFILE_MAX_BYTES:
                raise RuntimeError(f"Cura profile exceeds the cleanup size limit: {relative}")
            raw = path.read_bytes()
        except OSError as error:
            raise RuntimeError(f"Unable to read Cura profile for cleanup: {relative}") from error
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            plan.quarantines[relative] = raw
            continue

        strict_parser = _parser(strict=True)
        repaired = False
        try:
            strict_parser.read_string(text)
            parser = strict_parser
        except configparser.Error:
            # Duplicate sections/options are a common recoverable cause of Cura's
            # corrupt-profile warning. Parse them permissively, then serialize one
            # canonical instance-container document.
            parser = _parser(strict=False)
            try:
                parser.read_string(text)
            except configparser.Error:
                plan.quarantines[relative] = raw
                continue
            repaired = True
        if not _valid_quality_profile(parser):
            plan.quarantines[relative] = raw
            continue

        removed = 0
        if parser.has_section("values"):
            for key in list(parser["values"]):
                if key.casefold() in managed_setting_keys:
                    parser.remove_option("values", key)
                    removed += 1
        if not repaired and removed == 0:
            continue
        replacement = _serialize(parser)
        validation_parser = _parser(strict=True)
        try:
            validation_parser.read_string(replacement.decode("utf-8"))
        except configparser.Error as error:
            raise RuntimeError(f"Repaired Cura profile did not validate: {relative}") from error
        if not _valid_quality_profile(validation_parser):
            raise RuntimeError(f"Repaired Cura profile is incomplete: {relative}")
        plan.replacements[relative] = replacement
        plan.removed_setting_count += removed
        plan.repaired_profile_count += int(repaired)
    return plan


def quality_profiles_are_clean(root: Path, managed_setting_keys: frozenset[str]) -> bool:
    """Return whether every bounded user quality profile is valid and conflict-free."""

    try:
        plan = plan_quality_profile_cleanup(root, managed_setting_keys)
    except RuntimeError:
        return False
    return not plan.replacements and not plan.quarantines
