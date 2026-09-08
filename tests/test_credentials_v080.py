"""Shared-volume credential storage must fail closed on unsafe files or lost keys."""

from pathlib import Path

import pytest
from test_api_integration import integration_settings

from filament_manager.services.credentials import CredentialError, credential_cipher, decrypt_credential


def test_key_creation_permissions_and_no_regeneration(tmp_path: Path) -> None:
    settings = integration_settings("postgresql+psycopg://unused", tmp_path)
    with pytest.raises(CredentialError):
        credential_cipher(settings)
    cipher = credential_cipher(settings, create=True)
    ciphertext = cipher.encrypt(b"test-credential").decode()
    key = tmp_path / "credentials/integration.key"
    assert key.stat().st_mode & 0o777 == 0o600
    assert key.parent.stat().st_mode & 0o777 == 0o700
    assert decrypt_credential(settings, ciphertext) == "test-credential"
    key.rename(tmp_path / "retained.key")
    with pytest.raises(CredentialError):
        decrypt_credential(settings, ciphertext)
    assert not key.exists()


@pytest.mark.parametrize("target", ["integration.key", "key.lock"])
def test_rejects_linked_credential_files(tmp_path: Path, target: str) -> None:
    settings = integration_settings("postgresql+psycopg://unused", tmp_path)
    credential_cipher(settings, create=True)
    path = tmp_path / "credentials" / target
    path.rename(tmp_path / "retained")
    path.symlink_to(tmp_path / "retained")
    with pytest.raises(CredentialError):
        credential_cipher(settings)


def test_rejects_public_directory(tmp_path: Path) -> None:
    settings = integration_settings("postgresql+psycopg://unused", tmp_path)
    credential_cipher(settings, create=True)
    (tmp_path / "credentials").chmod(0o755)
    with pytest.raises(CredentialError):
        credential_cipher(settings)
