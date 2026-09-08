"""Explicit administrator-owned Moonraker endpoints and encrypted API credentials."""

import ipaddress
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import or_, select, text

from filament_manager.api.dependencies import Administrator, DatabaseSession
from filament_manager.api.errors import ApiError
from filament_manager.api.printer_safety import require_idle_printer
from filament_manager.api.schemas import PrinterResponse
from filament_manager.config import get_settings
from filament_manager.models.enums import JobStatus
from filament_manager.models.inventory import Printer, Spool
from filament_manager.models.operations import OutboxJob
from filament_manager.models.printing import PrintJob
from filament_manager.services.credentials import CredentialError, writable_cipher
from filament_manager.services.events import add_audit_event, add_outbox_job

router = APIRouter(prefix="/printers", tags=["printers"])


class ConnectionFields(BaseModel):
    """Only explicit endpoints; fixed Moonraker API paths, no supplied credentials in URLs."""

    model_config = ConfigDict(extra="forbid")
    base_url: str = Field(min_length=1, max_length=512)
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def safe_endpoint(cls, value: str) -> str:
        """Allow administrator-selected LAN/reverse-proxy origins, never metadata services."""
        try:
            parsed = urlsplit(value.strip())
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError
            if parsed.path not in {"", "/"} or parsed.port == 0:
                raise ValueError
            host = parsed.hostname.lower()
            if host.rstrip(".") in {
                "localhost",
                "metadata.google.internal",
                "metadata",
                "instance-data",
            } or host.endswith(".localhost"):
                raise ValueError
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address and (
                address.is_link_local or address.is_loopback or address.is_multicast or address.is_unspecified
            ):
                raise ValueError
        except ValueError:
            raise ValueError(
                "Use an HTTP or HTTPS Moonraker origin without a path, query, or embedded credentials."
            ) from None
        normalized_host = f"[{host}]" if ":" in host else host.rstrip(".").encode("idna").decode("ascii")
        port = parsed.port
        suffix = f":{port}" if port and port != (443 if parsed.scheme == "https" else 80) else ""
        return f"{parsed.scheme}://{normalized_host}{suffix}"


class PrinterCreate(ConnectionFields):
    name: str = Field(min_length=1, max_length=160)
    nozzle_diameter_mm: Decimal = Field(default=Decimal("0.4"), gt=0, le=10)
    extruder_count: int = Field(default=1, ge=1, le=16)
    heated_chamber: bool = False
    max_extruder_temp_c: Decimal | None = Field(default=None, gt=0, le=1000)
    max_bed_temp_c: Decimal | None = Field(default=None, ge=0, le=500)


class ConnectionUpdate(ConnectionFields):
    expected_version: int = Field(ge=1)
    clear_api_key: bool = False


async def encrypt_api_key(session: DatabaseSession, value: SecretStr | None) -> str | None:
    """Only newly submitted values enter encryption; never reveal existing secrets."""
    if value is None or not value.get_secret_value().strip():
        return None
    try:
        return (
            (await writable_cipher(session, get_settings()))
            .encrypt(value.get_secret_value().strip().encode())
            .decode()
        )
    except CredentialError as exc:
        raise ApiError(409, "credential_storage", str(exc)) from None


def record_change(
    session: DatabaseSession, request: Request, user: Administrator, printer: Printer, action: str
) -> None:
    """Audit identities only and queue independently authenticated connection discovery."""
    add_audit_event(
        session,
        actor_id=user.id,
        source="web",
        action=action,
        object_type="printer",
        object_id=printer.id,
        before=None,
        after={"record_version": printer.record_version},
        correlation_id=request.state.correlation_id,
    )
    for kind in ("moonraker.printer_info.reconcile", "moonraker.state.reconcile"):
        add_outbox_job(
            session,
            job_type=kind,
            idempotency_key=f"{kind}:{printer.id}:v{printer.record_version}",
            aggregate_type="printer",
            aggregate_id=printer.id,
            aggregate_version=printer.record_version,
            payload={"printer_id": str(printer.id)},
        )


@router.post("", response_model=PrinterResponse, status_code=201)
async def create_printer(
    payload: PrinterCreate, request: Request, user: Administrator, session: DatabaseSession
) -> PrinterResponse:
    """Add a live independent printer; never seize an existing deployment identity."""
    await session.execute(text("SELECT pg_advisory_xact_lock(460807080)"))
    if await session.scalar(
        select(Printer.id).where(Printer.moonraker_base_url.in_([payload.base_url, payload.base_url + "/"]))
    ):
        raise ApiError(
            409,
            "printer_connection_exists",
            "This Moonraker endpoint already belongs to a printer. Edit that printer instead.",
        )
    printer = Printer(
        id=uuid4(),
        printer_code="printer-" + uuid4().hex[:12],
        name=payload.name.strip(),
        moonraker_base_url=payload.base_url,
        connection_managed=True,
        connection_enabled=payload.enabled,
        encrypted_api_key=await encrypt_api_key(session, payload.api_key),
        nozzle_diameter_mm=payload.nozzle_diameter_mm,
        heated_chamber=payload.heated_chamber,
        extruder_count=payload.extruder_count,
        max_extruder_temp_c=payload.max_extruder_temp_c,
        max_bed_temp_c=payload.max_bed_temp_c,
    )
    if not printer.name:
        raise ApiError(422, "printer_name", "Enter a printer name.")
    session.add(printer)
    await session.flush()
    record_change(session, request, user, printer, "printer.create")
    response = PrinterResponse.model_validate(printer)
    await session.commit()
    return response


@router.get("/{printer_id}/connection")
async def connection_status(
    printer_id: UUID, user: Administrator, session: DatabaseSession
) -> dict[str, object]:
    """Explicit private settings view; API keys remain write-only."""
    printer = await session.get(Printer, printer_id)
    if printer is None:
        raise ApiError(404, "unknown_printer", "Printer not found.")
    legacy = next(
        (item for item in get_settings().moonraker.printers if item.id == printer.printer_code), None
    )
    return {
        "base_url": str(legacy.base_url).rstrip("/")
        if legacy and not printer.connection_managed
        else printer.moonraker_base_url,
        "enabled": printer.connection_enabled,
        "managed": printer.connection_managed,
        "has_api_key": bool(printer.encrypted_api_key)
        if printer.connection_managed
        else bool(legacy and (legacy.api_key or legacy.api_key_file)),
        "record_version": printer.record_version,
    }


@router.put("/{printer_id}/connection", response_model=PrinterResponse)
async def update_connection(
    printer_id: UUID,
    payload: ConnectionUpdate,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> PrinterResponse:
    """Adopt or edit a connection with optimistic concurrency and live idle protection."""
    await session.execute(text("SELECT pg_advisory_xact_lock(460807080)"))
    printer = await session.get(Printer, printer_id, with_for_update=True)
    if printer is None:
        raise ApiError(404, "unknown_printer", "Printer not found.")
    if printer.record_version != payload.expected_version:
        raise ApiError(409, "record_version_conflict", "Printer changed; reload.")
    # Endpoint changes must not redirect an active printer's pending commands.
    if payload.base_url != printer.moonraker_base_url.rstrip("/") or not payload.enabled:
        pending = await session.scalar(
            select(OutboxJob.id)
            .where(
                OutboxJob.job_type.in_(
                    (
                        "moonraker.spool_change.request",
                        "moonraker.active_spool.set",
                        "moonraker.spool_unload.request",
                        "moonraker.build_plate.select",
                        "moonraker.build_plate.clear",
                    )
                ),
                OutboxJob.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)),
                or_(
                    OutboxJob.payload["printer_id"].astext == str(printer.id),
                    OutboxJob.payload["printer_id"].astext.is_(None),
                ),
            )
            .limit(1)
        )
        if pending:
            raise ApiError(
                409,
                "printer_commands_pending",
                "Wait for pending physical printer commands before changing this connection.",
            )
        # A newly entered, never-contacted endpoint can be corrected before it
        # owns physical context. Established printers remain fail-closed offline.
        pristine = (
            printer.connection_managed
            and printer.last_seen_at is None
            and printer.active_plate_id is None
            and not await session.scalar(
                select(Spool.id).where(Spool.active_printer_id == printer.id).limit(1)
            )
            and not await session.scalar(
                select(PrintJob.id).where(PrintJob.printer_id == printer.id).limit(1)
            )
        )
        if not pristine:
            await require_idle_printer(printer.printer_code, get_settings(), session)
    if await session.scalar(
        select(Printer.id).where(
            Printer.id != printer.id,
            Printer.moonraker_base_url.in_([payload.base_url, payload.base_url + "/"]),
        )
    ):
        raise ApiError(
            409, "printer_connection_exists", "This Moonraker endpoint already belongs to another printer."
        )
    if payload.clear_api_key:
        printer.encrypted_api_key = None
    elif payload.api_key and payload.api_key.get_secret_value().strip():
        printer.encrypted_api_key = await encrypt_api_key(session, payload.api_key)
    elif not printer.connection_managed:
        legacy = next(
            (item for item in get_settings().moonraker.printers if item.id == printer.printer_code), None
        )
        legacy_key = legacy.resolved_api_key() if legacy else None
        printer.encrypted_api_key = (
            await encrypt_api_key(session, SecretStr(legacy_key)) if legacy_key else None
        )
    printer.moonraker_base_url = payload.base_url
    printer.connection_enabled = payload.enabled
    printer.connection_managed = True
    printer.record_version += 1
    record_change(session, request, user, printer, "printer.connection.update")
    response = PrinterResponse.model_validate(printer)
    await session.commit()
    return response
