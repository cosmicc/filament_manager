"""Managed Cura edit scope tests."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from filament_manager.api.schemas import CuraManagedMaterialReport


@pytest.mark.parametrize(
    "extra",
    [
        {"edited_settings": {"machine_start_gcode": "G28"}},
        {"edited_settings": {"material_flow": "1" * 501}},
        {"edited_settings": {"material_flow": "95\n100"}},
        {"edit_ids": {"material_flow": str(uuid4())}},
        {"edited_settings": {"material_flow": "95"}, "edit_ids": {"material_flow": "invalid"}},
    ],
)
def test_explicit_edit_evidence_is_bounded_and_allowlisted(extra: dict[str, object]) -> None:
    """New provenance fields never bypass the material setting input boundary."""

    with pytest.raises(ValidationError):
        CuraManagedMaterialReport.model_validate(
            {
                "source_id": "a" * 64,
                "installation_id": "test",
                "name": "PLA",
                "brand": "Unknown",
                "material_type": "PLA",
                "color_name": "Black",
                "material_guid": str(uuid4()),
                "content_checksum": "b" * 64,
                "settings": {},
                **extra,
            }
        )
