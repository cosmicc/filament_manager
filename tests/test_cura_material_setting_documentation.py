"""Keep the operator-facing Cura Material Settings list aligned with code."""

import re
from pathlib import Path

from filament_manager.domain.cura_material_settings import CURA_MATERIAL_SETTINGS

DOCUMENTED_SETTING = re.compile(r"^([a-z][a-z0-9_]*)\s+\|\s+([^|]+?)\s+\|")


def test_cura_material_print_setting_list_matches_the_central_catalog() -> None:
    """Every editable catalog key and label appears exactly once in the text list."""

    document = Path(__file__).parents[1] / "docs" / "CURA_MATERIAL_PRINT_SETTINGS.txt"
    documented: dict[str, str] = {}
    for line in document.read_text(encoding="utf-8").splitlines():
        match = DOCUMENTED_SETTING.match(line)
        if match is None:
            continue
        key, label = match.groups()
        assert key not in documented, f"Duplicate documented Cura material setting: {key}"
        documented[key] = label.strip()

    expected = {setting.key: setting.label for setting in CURA_MATERIAL_SETTINGS if setting.editable}
    assert documented == expected
