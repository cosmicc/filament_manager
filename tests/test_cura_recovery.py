"""Sanitized Cura recovery snapshot contract tests."""

import pytest

from filament_manager.domain.cura_recovery import (
    recovery_checksum,
    suspected_reset,
    validate_recovery_payload,
)


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "installation_id": "cura-test",
        "cura_version": "5.13",
        "setting_version": 27,
        "files": [
            {
                "scope": "data",
                "relative_path": "machine_instances/Workshop.global.cfg",
                "content": "[general]\nname = Workshop Printer\n",
            },
            {
                "scope": "config",
                "relative_path": "cura.cfg",
                "content": "[general]\ntheme = dark\n\n[cura]\nactive_machine = workshop\n",
            },
        ],
        "plugins": [
            {
                "package_id": "MaterialSettingsPlugin",
                "display_name": "Material Settings",
                "version": "4.3.1",
                "enabled": True,
            }
        ],
    }


def test_recovery_payload_is_bounded_and_content_addressed() -> None:
    payload = _payload()

    assert validate_recovery_payload(payload) == (2, 91)
    assert recovery_checksum(payload) == recovery_checksum(_payload())


@pytest.mark.parametrize(
    "content",
    [
        "[general]\nultimaker_auth_data = secret\n",
        "[general]\napiKey = secret\n",
        "[general]\nauthToken = secret\n",
        "[general]\nserver_url = https://printer.example\n",
        "[general]\nlast_folder = /home/operator/models\n",
        "[general]\ncache_file = /srv/cura-private-state\n",
    ],
)
def test_recovery_payload_rejects_secrets_endpoints_and_paths(content: str) -> None:
    payload = _payload()
    payload["files"] = [
        {
            "scope": "config",
            "relative_path": "cura.cfg",
            "content": content,
        }
    ]

    with pytest.raises(ValueError):
        validate_recovery_payload(payload)


def test_recovery_payload_rejects_sensitive_plugin_display_metadata() -> None:
    payload = _payload()
    payload["plugins"] = [
        {
            "package_id": "BadMetadata",
            "display_name": "/srv/private-plugin-path",
            "version": "1.0.0",
            "enabled": True,
        }
    ]

    with pytest.raises(ValueError):
        validate_recovery_payload(payload)


def test_recovery_payload_accepts_cura_key_only_visibility_presets() -> None:
    """Cura visibility presets use valid entries without ``= value`` suffixes."""

    content = "[values]\nlayer_height\nspeed_print\nspeed_ironing\n"
    payload = _payload()
    payload["files"] = [
        {
            "scope": "data",
            "relative_path": "setting_visibility/my+advanced+set.cfg",
            "content": content,
        }
    ]

    assert validate_recovery_payload(payload) == (1, len(content.encode("utf-8")))


def test_recovery_payload_keeps_other_cura_configuration_strict() -> None:
    """Key-only syntax is accepted only for Cura setting-visibility presets."""

    payload = _payload()
    payload["files"] = [
        {
            "scope": "data",
            "relative_path": "quality_changes/invalid.inst.cfg",
            "content": "[values]\nlayer_height\n",
        }
    ]

    with pytest.raises(ValueError, match="valid bounded INI"):
        validate_recovery_payload(payload)


def test_reset_detection_preserves_last_known_good_configuration() -> None:
    assert suspected_reset(
        previous_machine_count=2,
        previous_file_count=20,
        previous_quality_profile_count=6,
        machine_count=1,
        file_count=4,
        quality_profile_count=1,
    )
    assert not suspected_reset(
        previous_machine_count=1,
        previous_file_count=20,
        previous_quality_profile_count=6,
        machine_count=1,
        file_count=19,
        quality_profile_count=5,
    )
