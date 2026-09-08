"""Coalesced, retryable full business publication without printer requests."""

import asyncio
from datetime import UTC, datetime, timedelta

from google.auth.transport.requests import Request as GoogleRequest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from filament_manager.clients.google_sheets import GoogleSheetsClient, GoogleSheetsError
from filament_manager.clients.google_workbook import GoogleWorkbookClient
from filament_manager.config import get_settings
from filament_manager.models.enums import PrintJobStatus
from filament_manager.models.google import GoogleConnection
from filament_manager.models.printing import PrintJob
from filament_manager.services.google_connection import GOOGLE_LOCK, access_token, connection
from filament_manager.services.google_workbook import fingerprint, snapshot


async def publication_enabled(session: AsyncSession) -> bool:
    """Support existing service-account deployments and new OAuth connections."""
    return get_settings().google.enabled or bool(
        await session.scalar(select(GoogleConnection.refresh_token).where(GoogleConnection.id == 1))
    )


async def publish(session: AsyncSession, *, force: bool = False) -> None:
    """Publish a consistent snapshot; periodic comparison covers every mutation.

    Existing targeted outbox events provide early delivery. The periodic content
    comparison also catches deletes, archived/history edits and missed events.
    A shared lock serializes publishers and disconnect. No business row is locked.
    """
    settings = get_settings()
    if not await publication_enabled(session):
        return
    active = await session.scalar(
        select(PrintJob.id).where(PrintJob.status == PrintJobStatus.IN_PROGRESS).limit(1)
    )
    if active:
        return
    acquired = await session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": GOOGLE_LOCK})
    if not acquired:
        # Do not occupy another worker waiting behind a large upload. The
        # periodic complete comparison catches changes made during this pass.
        return
    record = await connection(session)
    # Recheck after the lock: a concurrent disconnect must stop publication.
    if not record.refresh_token and not settings.google.enabled:
        return
    now = datetime.now(UTC)
    if record.next_attempt_at and record.next_attempt_at > now:
        return
    requested = bool(record.sync_requested_at) or force
    if (
        not requested
        and record.last_synced_at
        and now - record.last_synced_at < timedelta(seconds=settings.google.publish_interval_seconds)
    ):
        return
    try:
        # A separate read-only transaction gives one consistent generation and
        # ends before Google network I/O. It cannot lock canonical business rows.
        bind = session.bind
        assert bind is not None
        async with AsyncSession(bind=bind) as reader:
            await reader.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            tables = await snapshot(reader)
        digest = fingerprint(tables)
        if not requested and digest == record.last_fingerprint:
            # Canonical data may have reverted while a previous upload failed.
            # The last good workbook already matches this exact generation.
            record.last_error = None
            record.failures = 0
            record.next_attempt_at = None
            await session.commit()
            return
        if settings.google.enabled:
            record.mode = "service_account"
            legacy = GoogleSheetsClient(
                settings.google.spreadsheet_id or "",
                settings.google.service_account_file,
                settings.google.resolved_service_account_info(),
            )
            try:
                await asyncio.to_thread(legacy.credentials.refresh, GoogleRequest())
            except Exception:
                raise GoogleSheetsError(
                    "Google service-account authorization failed. Check deployment credentials."
                ) from None
            token = legacy.credentials.token
            assert token is not None
            record.spreadsheet_id = settings.google.spreadsheet_id
        else:
            token = await access_token(record)
        client = GoogleWorkbookClient(token, record.publication_key)
        if not record.spreadsheet_id:
            record.spreadsheet_id = await client.find_or_create()
        await client.publish(record.spreadsheet_id, tables)
        record.last_fingerprint = digest
        record.last_synced_at = datetime.now(UTC)
        record.sync_requested_at = None
        record.last_error = None
        record.failures = 0
        record.next_attempt_at = None
        await session.commit()
    except GoogleSheetsError as exc:
        record.last_error = str(exc)
        record.failures += 1
        record.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=min(3600, 60 * 2 ** min(record.failures - 1, 6))
        )
        await session.commit()
        raise
