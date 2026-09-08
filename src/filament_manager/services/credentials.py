"""Private, shared-volume credential encryption for administrator integrations.

The key never lives in PostgreSQL or an API response. Creation is explicit and
serialized across web/worker processes; missing keys never regenerate on read.
"""

import fcntl
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.config import Settings
from filament_manager.models.google import GoogleConnection
from filament_manager.models.inventory import Printer


class CredentialError(Exception):
    """Safe, value-free credential storage failure."""


def credential_cipher(settings: Settings, *, create: bool = False) -> Fernet:
    """Use the existing explicit key or a private persistent shared-volume key."""
    supplied = settings.google.token_encryption_key
    try:
        if supplied is not None:
            return Fernet(supplied.get_secret_value().encode("ascii"))
        directory = Path(settings.app.data_dir) / "credentials"
        if create:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError
        lock_fd = os.open(directory / "key.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(lock_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            path = directory / "integration.key"
            if create and not path.exists():
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                try:
                    os.write(fd, Fernet.generate_key())
                    os.fsync(fd)
                finally:
                    os.close(fd)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise ValueError
                key = os.read(fd, 128)
            finally:
                os.close(fd)
            return Fernet(key)
        finally:
            os.close(lock_fd)
    except (OSError, ValueError, UnicodeError):
        raise CredentialError(
            "Private credential storage is unavailable. Check the shared data volume and its encryption key."
        ) from None


async def writable_cipher(session: AsyncSession, settings: Settings) -> Fernet:
    """Initialize once, never replacing a lost key that protects existing data.

    The transaction lock covers the ciphertext check and caller's database write.
    The filesystem lock also serializes readers in separate application processes.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(460807081)"))
    encrypted_printer = await session.scalar(
        select(Printer.id).where(Printer.encrypted_api_key.is_not(None)).limit(1)
    )
    encrypted_google = await session.scalar(
        select(GoogleConnection.id)
        .where(
            or_(
                GoogleConnection.refresh_token.is_not(None),
                GoogleConnection.oauth_client_secret.is_not(None),
                GoogleConnection.verifier.is_not(None),
            )
        )
        .limit(1)
    )
    return credential_cipher(settings, create=encrypted_printer is None and encrypted_google is None)


def decrypt_credential(settings: Settings, value: str) -> str:
    """Decrypt only at the outbound boundary with no secret-bearing errors."""
    try:
        return credential_cipher(settings).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        raise CredentialError("Stored credentials cannot be decrypted. Restore the encryption key.") from None
