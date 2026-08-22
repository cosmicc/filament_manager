"""Secure workstation enrollment and leased Cura profile deployment APIs."""

import hashlib
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import delete, or_, select, update

from filament_manager.config import get_settings
from filament_manager.domain.cura_import import material_settings_from_cura, merge_cura_settings
from filament_manager.domain.cura_recovery import (
    RECOVERY_HISTORY_LIMIT,
    recovery_checksum,
    suspected_reset,
    validate_recovery_payload,
)
from filament_manager.models.enums import CuraDeploymentStatus, ProfileStatus
from filament_manager.models.inventory import (
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
    Printer,
)
from filament_manager.models.workstations import (
    CuraDeployment,
    CuraRecoveryRestore,
    CuraRecoverySnapshot,
    CuraTakeoverMapping,
    WorkstationAgent,
    WorkstationPairingCode,
)
from filament_manager.security import create_agent_token, create_pairing_code, hash_token
from filament_manager.services.cura_edits import import_managed_cura_edits
from filament_manager.services.cura_library import (
    build_cura_library,
    queue_cura_library,
    settings_from_template,
)
from filament_manager.services.cura_nozzles import queue_cura_nozzle_update
from filament_manager.services.events import add_audit_event
from filament_manager.services.material_settings import save_template_settings

from ..dependencies import Administrator, CurrentWorkstationAgent, DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    CuraDeploymentClaimResponse,
    CuraDeploymentCompletion,
    CuraDeploymentCreate,
    CuraDeploymentResponse,
    CuraRecoveryCaptureRequest,
    CuraRecoveryRestoreClaimResponse,
    CuraRecoveryRestoreCompletion,
    CuraRecoveryRestoreRequest,
    CuraRecoveryRestoreResponse,
    CuraRecoverySnapshotDelete,
    CuraRecoverySnapshotResponse,
    CuraRecoverySnapshotUpdate,
    CuraRecoverySnapshotUpload,
    CuraRecoverySnapshotUploadResponse,
    CuraTakeoverRequest,
    MaterialSettingsInput,
    WorkstationAgentResponse,
    WorkstationAgentUpdate,
    WorkstationHeartbeat,
    WorkstationPairingCodeResponse,
    WorkstationPairRequest,
    WorkstationPairResponse,
)

router = APIRouter(tags=["Cura workstations"])
PAIRING_LIFETIME = timedelta(minutes=10)
CLAIM_LEASE = timedelta(minutes=5)
MAX_AGENT_JSON_BYTES = 2 * 1024 * 1024
MAX_RECOVERY_JSON_BYTES = 3 * 1024 * 1024
SAFE_AGENT_ERROR_MESSAGES = frozenset(
    {
        "No Cura printer configuration was found to back up.",
        "Cura appears to have been reset; the last known-good automatic backup was preserved.",
        "This automatic backup was previously deleted and remains suppressed.",
        "A supported Cura settings directory failed the local safety check.",
        "The Cura settings backup exceeds the safe file or size limit.",
        "Cura settings could not be captured safely on the workstation.",
    }
)


def _sanitized_agent_error(value: str | None) -> str | None:
    """Keep only path-free agent guidance safe for web and diagnostics output."""

    if value is None:
        return None
    normalized = " ".join(value.split())
    if normalized in SAFE_AGENT_ERROR_MESSAGES:
        return normalized
    return "The workstation agent reported an error. Review its local service log."


class PairingRateLimiter:
    """Bound enrollment attempts by client address without retaining request data."""

    def __init__(self, attempts: int = 10, window_seconds: int = 300) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = self._events[key]
        while events and events[0] < now - self.window_seconds:
            events.popleft()
        if len(events) >= self.attempts:
            return False
        events.append(now)
        return True


pairing_limiter = PairingRateLimiter()


def _bounded_json(value: object, *, max_bytes: int = MAX_AGENT_JSON_BYTES) -> None:
    """Reject oversized agent metadata before it reaches PostgreSQL or audit logs."""

    if len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8")) > max_bytes:
        raise ApiError(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "agent_metadata_too_large",
            "Agent metadata is too large",
        )


def _public_pairing_transport_is_safe() -> bool:
    """Require the configured public URL to use TLS except for loopback development."""

    parsed = urlparse(str(get_settings().app.base_url))
    return parsed.scheme == "https" or parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _unmanaged_cura_source_count(capabilities: dict[str, object]) -> int | None:
    """Return the combined takeover count with backward compatibility."""

    combined = capabilities.get("unmanaged_import_source_count")
    if isinstance(combined, int) and not isinstance(combined, bool) and combined >= 0:
        return combined
    materials = capabilities.get("unmanaged_material_count")
    if isinstance(materials, int) and not isinstance(materials, bool) and materials >= 0:
        return materials
    return None


def _reported_cura_installation(
    agent: WorkstationAgent,
    installation_id: str,
    cura_version: str,
) -> dict[str, object] | None:
    """Match a path-free recovery request to the agent's current exact Cura version."""

    return next(
        (
            item
            for item in agent.cura_installations
            if isinstance(item, dict)
            and item.get("installation_id") == installation_id
            and item.get("version") == cura_version
        ),
        None,
    )


def _recovery_snapshot_response(snapshot: CuraRecoverySnapshot) -> CuraRecoverySnapshotResponse:
    """Expose snapshot metadata and plugin inventory without raw configuration files."""

    raw_plugins = snapshot.payload.get("plugins", [])
    plugins = (
        [item for item in raw_plugins if isinstance(item, dict)] if isinstance(raw_plugins, list) else []
    )
    return CuraRecoverySnapshotResponse(
        id=snapshot.id,
        agent_id=snapshot.agent_id,
        installation_id=snapshot.installation_id,
        cura_version=snapshot.cura_version,
        setting_version=snapshot.setting_version,
        snapshot_checksum=snapshot.snapshot_checksum,
        file_count=snapshot.file_count,
        total_bytes=snapshot.total_bytes,
        machine_count=snapshot.machine_count,
        quality_profile_count=snapshot.quality_profile_count,
        plugin_count=snapshot.plugin_count,
        plugins=plugins,
        capture_kind=snapshot.capture_kind,
        name=snapshot.name,
        description=snapshot.description,
        record_version=snapshot.record_version,
        captured_at=snapshot.captured_at,
        created_at=snapshot.created_at,
    )


def _recovery_suppression_key(installation_id: str, cura_version: str, checksum: str) -> str:
    """Identify one operator-deleted automatic snapshot without retaining its payload."""

    return f"{installation_id}:{cura_version}:{checksum}"


@router.post(
    "/workstation-agents/pairing-codes",
    response_model=WorkstationPairingCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workstation_pairing_code(
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> WorkstationPairingCodeResponse:
    """Create a ten-minute pairing code whose plaintext is returned once."""

    if not _public_pairing_transport_is_safe():
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "pairing_requires_https",
            "Configure an HTTPS public base URL before pairing a workstation",
        )
    raw_code = create_pairing_code()
    now = datetime.now(UTC)
    pairing = WorkstationPairingCode(
        code_hash=hash_token(raw_code),
        expires_at=now + PAIRING_LIFETIME,
        created_by=administrator.id,
        created_at=now,
    )
    session.add(pairing)
    await session.flush()
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="workstation.pairing_code.create",
        object_type="workstation_pairing_code",
        object_id=pairing.id,
        before=None,
        after={"expires_at": pairing.expires_at.isoformat()},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return WorkstationPairingCodeResponse(pairing_code=raw_code, expires_at=pairing.expires_at)


@router.post(
    "/workstation-agent/pair",
    response_model=WorkstationPairResponse,
    status_code=status.HTTP_201_CREATED,
)
async def pair_workstation(
    payload: WorkstationPairRequest,
    request: Request,
    session: DatabaseSession,
) -> WorkstationPairResponse:
    """Consume a one-time code and return one scoped agent credential."""

    client_key = request.client.host if request.client else "unknown"
    if not pairing_limiter.allow(client_key):
        raise ApiError(status.HTTP_429_TOO_MANY_REQUESTS, "pairing_rate_limited", "Try again later")
    if not _public_pairing_transport_is_safe():
        raise ApiError(status.HTTP_403_FORBIDDEN, "pairing_requires_https", "Secure pairing is unavailable")
    _bounded_json(
        {
            "capabilities": payload.capabilities,
            "cura_installations": payload.cura_installations,
            "cura_materials": payload.cura_materials,
            "cura_managed_materials": payload.cura_managed_materials,
        }
    )
    now = datetime.now(UTC)
    pairing = await session.scalar(
        select(WorkstationPairingCode)
        .where(WorkstationPairingCode.code_hash == hash_token(payload.pairing_code))
        .with_for_update()
    )
    if pairing is None or pairing.consumed_at is not None or pairing.expires_at <= now:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "pairing_code_invalid", "Pairing code is invalid or expired"
        )
    raw_token = create_agent_token()
    agent = WorkstationAgent(
        agent_code=f"WS-{secrets.token_hex(8).upper()}",
        display_name=payload.display_name.strip(),
        hostname=payload.hostname.strip(),
        platform=payload.platform,
        architecture=payload.architecture,
        agent_version=payload.agent_version,
        token_hash=hash_token(raw_token),
        cura_management_enabled=(
            bool(payload.cura_installations) and _unmanaged_cura_source_count(payload.capabilities) == 0
        ),
        capabilities=payload.capabilities,
        cura_installations=[item.model_dump(mode="json") for item in payload.cura_installations],
        cura_materials=[item.model_dump(mode="json") for item in payload.cura_materials],
        last_seen_at=now,
        created_by=pairing.created_by,
    )
    session.add(agent)
    await session.flush()
    pairing.consumed_at = now
    pairing.consumed_by_agent_id = agent.id
    add_audit_event(
        session,
        actor_id=pairing.created_by,
        source="workstation_agent",
        action="workstation.pair",
        object_type="workstation_agent",
        object_id=agent.id,
        before=None,
        after={"agent_code": agent.agent_code, "platform": agent.platform, "hostname": agent.hostname},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return WorkstationPairResponse(agent_id=agent.id, agent_code=agent.agent_code, agent_token=raw_token)


@router.post("/workstation-agent/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def workstation_heartbeat(
    payload: WorkstationHeartbeat,
    request: Request,
    agent: CurrentWorkstationAgent,
    session: DatabaseSession,
) -> Response:
    """Refresh discovery data while keeping local file paths off the server."""

    _bounded_json(
        {
            "capabilities": payload.capabilities,
            "cura_installations": payload.cura_installations,
            "cura_materials": payload.cura_materials,
            "cura_managed_materials": payload.cura_managed_materials,
        }
    )
    agent.agent_version = payload.agent_version
    agent.capabilities = payload.capabilities
    agent.cura_installations = [item.model_dump(mode="json") for item in payload.cura_installations]
    agent.cura_materials = [item.model_dump(mode="json") for item in payload.cura_materials]
    agent.last_seen_at = datetime.now(UTC)
    agent.last_error = _sanitized_agent_error(payload.last_error)
    if (
        not agent.cura_management_enabled
        and payload.cura_installations
        and _unmanaged_cura_source_count(payload.capabilities) == 0
    ):
        agent.cura_management_enabled = True
    agent.record_version += 1
    if agent.cura_management_enabled and payload.cura_installations:
        await import_managed_cura_edits(
            session,
            agent=agent,
            reports=payload.cura_managed_materials,
            correlation_id=request.state.correlation_id,
        )
        try:
            desired = await build_cura_library(session)
            materials = desired.get("materials")
            desired_checksum = desired.get("library_checksum")
            current_checksums = {item.managed_library_checksum for item in payload.cura_installations}
            if (
                isinstance(materials, list)
                and materials
                and isinstance(desired_checksum, str)
                and current_checksums != {desired_checksum}
            ):
                await queue_cura_library(
                    session,
                    [agent],
                    requested_by=None,
                    force=True,
                    retry_failed=False,
                )
        except ValueError:
            # An empty desired library is valid during first-time configuration;
            # never hide Cura materials until canonical settings exist.
            pass
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workstation-agents", response_model=list[WorkstationAgentResponse])
async def list_workstation_agents(_: Viewer, session: DatabaseSession) -> list[WorkstationAgentResponse]:
    """List paired workstations without credential material."""

    agents = await session.scalars(select(WorkstationAgent).order_by(WorkstationAgent.display_name))
    return [WorkstationAgentResponse.model_validate(agent) for agent in agents]


@router.post(
    "/workstation-agent/cura-recovery-snapshots",
    response_model=CuraRecoverySnapshotUploadResponse,
)
async def upload_cura_recovery_snapshot(
    payload: CuraRecoverySnapshotUpload,
    request: Request,
    agent: CurrentWorkstationAgent,
    session: DatabaseSession,
) -> CuraRecoverySnapshotUploadResponse:
    """Accept one bounded sanitized snapshot unless it resembles a destructive reset."""

    _bounded_json(payload.payload, max_bytes=MAX_RECOVERY_JSON_BYTES)
    try:
        file_count, total_bytes = validate_recovery_payload(payload.payload)
        expected_checksum = recovery_checksum(payload.payload)
    except ValueError as error:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_recovery_snapshot_invalid",
            str(error),
        ) from error
    if payload.snapshot_checksum != expected_checksum:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_recovery_checksum_mismatch",
            "Cura recovery snapshot checksum does not match its contents",
        )
    installation_id = payload.payload.get("installation_id")
    cura_version = payload.payload.get("cura_version")
    setting_version = payload.payload.get("setting_version")
    if (
        not isinstance(installation_id, str)
        or not isinstance(cura_version, str)
        or (
            setting_version is not None
            and (not isinstance(setting_version, int) or isinstance(setting_version, bool))
        )
        or _reported_cura_installation(agent, installation_id, cura_version) is None
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_recovery_installation_changed",
            "The exact Cura installation is no longer reported by this workstation",
        )
    raw_files = payload.payload.get("files")
    files = [item for item in raw_files if isinstance(item, dict)] if isinstance(raw_files, list) else []
    machine_count = sum(
        1
        for item in files
        if item.get("scope") == "data" and str(item.get("relative_path", "")).startswith("machine_instances/")
    )
    quality_profile_count = sum(
        1
        for item in files
        if item.get("scope") == "data"
        and str(item.get("relative_path", "")).split("/", 1)[0] in {"quality", "quality_changes"}
    )
    raw_plugins = payload.payload.get("plugins")
    plugin_count = len(raw_plugins) if isinstance(raw_plugins, list) else 0
    capture_request: CuraDeployment | None = None
    if payload.capture_request_id is not None:
        capture_request = await session.scalar(
            select(CuraDeployment).where(CuraDeployment.id == payload.capture_request_id).with_for_update()
        )
        capture_payload = capture_request.payload if capture_request is not None else {}
        if (
            capture_request is None
            or capture_request.agent_id != agent.id
            or capture_request.status != CuraDeploymentStatus.CLAIMED
            or capture_payload.get("operation") != "recovery_capture"
            or capture_payload.get("installation_id") != installation_id
            or capture_payload.get("cura_version") != cura_version
        ):
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "cura_recovery_capture_request_invalid",
                "The manual Cura backup request is no longer valid",
            )
    suppression_key = _recovery_suppression_key(
        installation_id,
        cura_version,
        payload.snapshot_checksum,
    )
    if capture_request is None and suppression_key in agent.suppressed_recovery_snapshots:
        return CuraRecoverySnapshotUploadResponse(
            accepted=False,
            status=agent.cura_recovery_status,
            reason="deleted_by_administrator",
            snapshot_checksum=payload.snapshot_checksum,
        )
    latest = await session.scalar(
        select(CuraRecoverySnapshot)
        .where(
            CuraRecoverySnapshot.agent_id == agent.id,
            CuraRecoverySnapshot.installation_id == installation_id,
            CuraRecoverySnapshot.cura_version == cura_version,
        )
        .order_by(CuraRecoverySnapshot.captured_at.desc())
        .limit(1)
    )
    if machine_count == 0:
        agent.cura_recovery_status = "capture_blocked" if latest else "not_ready"
        agent.cura_recovery_message = (
            "No printer configuration was captured. Add a Cura printer or restore the last recovery point."
        )
        agent.record_version += 1
        await session.commit()
        return CuraRecoverySnapshotUploadResponse(
            accepted=False,
            status=agent.cura_recovery_status,
            reason="no_printer_configuration",
            snapshot_id=latest.id if latest else None,
            snapshot_checksum=payload.snapshot_checksum,
        )
    if (
        capture_request is None
        and latest
        and suspected_reset(
            previous_machine_count=latest.machine_count,
            previous_file_count=latest.file_count,
            previous_quality_profile_count=latest.quality_profile_count,
            machine_count=machine_count,
            file_count=file_count,
            quality_profile_count=quality_profile_count,
        )
    ):
        agent.cura_recovery_status = "capture_blocked"
        agent.cura_recovery_message = (
            "A large Cura configuration deletion was detected. "
            "The last known-good recovery point was preserved."
        )
        agent.record_version += 1
        await session.commit()
        return CuraRecoverySnapshotUploadResponse(
            accepted=False,
            status="capture_blocked",
            reason="suspected_reset",
            snapshot_id=latest.id,
            snapshot_checksum=payload.snapshot_checksum,
        )
    existing = await session.scalar(
        select(CuraRecoverySnapshot).where(
            CuraRecoverySnapshot.capture_request_id == payload.capture_request_id
            if payload.capture_request_id is not None
            else (
                (CuraRecoverySnapshot.agent_id == agent.id)
                & (CuraRecoverySnapshot.installation_id == installation_id)
                & (CuraRecoverySnapshot.cura_version == cura_version)
                & (CuraRecoverySnapshot.snapshot_checksum == payload.snapshot_checksum)
                & (CuraRecoverySnapshot.capture_request_id.is_(None))
            )
        )
    )
    now = datetime.now(UTC)
    if existing is None:
        existing = CuraRecoverySnapshot(
            agent_id=agent.id,
            capture_request_id=payload.capture_request_id,
            created_by=capture_request.requested_by if capture_request is not None else None,
            capture_kind="manual" if capture_request is not None else "automatic",
            name=(str(capture_request.payload.get("name")) if capture_request is not None else None),
            description=(
                str(capture_request.payload["description"])
                if capture_request is not None and capture_request.payload.get("description")
                else None
            ),
            installation_id=installation_id,
            cura_version=cura_version,
            setting_version=setting_version,
            snapshot_checksum=payload.snapshot_checksum,
            payload=payload.payload,
            file_count=file_count,
            total_bytes=total_bytes,
            machine_count=machine_count,
            quality_profile_count=quality_profile_count,
            plugin_count=plugin_count,
            captured_at=now,
            created_at=now,
        )
        session.add(existing)
        await session.flush()
        history_ids = list(
            await session.scalars(
                select(CuraRecoverySnapshot.id)
                .where(
                    CuraRecoverySnapshot.agent_id == agent.id,
                    CuraRecoverySnapshot.installation_id == installation_id,
                    CuraRecoverySnapshot.cura_version == cura_version,
                )
                .order_by(CuraRecoverySnapshot.captured_at.desc())
                .offset(RECOVERY_HISTORY_LIMIT)
            )
        )
        if history_ids:
            await session.execute(
                delete(CuraRecoverySnapshot).where(CuraRecoverySnapshot.id.in_(history_ids))
            )
        add_audit_event(
            session,
            actor_id=None,
            source="workstation_agent",
            action="cura.recovery_snapshot.capture_manual"
            if capture_request
            else "cura.recovery_snapshot.capture",
            object_type="cura_recovery_snapshot",
            object_id=existing.id,
            before=None,
            after={
                "agent_code": agent.agent_code,
                "cura_version": cura_version,
                "file_count": file_count,
                "machine_count": machine_count,
                "quality_profile_count": quality_profile_count,
                "plugin_count": plugin_count,
                "capture_kind": existing.capture_kind,
            },
            correlation_id=request.state.correlation_id,
        )
    agent.cura_recovery_status = "ready"
    agent.cura_recovery_message = None
    agent.last_recovery_snapshot_at = existing.captured_at
    agent.record_version += 1
    await session.commit()
    return CuraRecoverySnapshotUploadResponse(
        accepted=True,
        status="ready",
        snapshot_id=existing.id,
        snapshot_checksum=existing.snapshot_checksum,
    )


@router.get(
    "/workstation-agents/{agent_id}/cura-recovery-snapshots",
    response_model=list[CuraRecoverySnapshotResponse],
)
async def list_cura_recovery_snapshots(
    agent_id: UUID,
    _: Viewer,
    session: DatabaseSession,
) -> list[CuraRecoverySnapshotResponse]:
    """List the retained recovery metadata for one paired workstation."""

    agent = await session.get(WorkstationAgent, agent_id)
    if agent is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "workstation_unknown", "Workstation not found")
    snapshots = await session.scalars(
        select(CuraRecoverySnapshot)
        .where(CuraRecoverySnapshot.agent_id == agent_id)
        .order_by(CuraRecoverySnapshot.captured_at.desc())
        .limit(RECOVERY_HISTORY_LIMIT * 20)
    )
    return [_recovery_snapshot_response(snapshot) for snapshot in snapshots]


@router.post(
    "/workstation-agents/{agent_id}/cura-recovery-captures",
    response_model=CuraDeploymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_cura_recovery_capture(
    agent_id: UUID,
    payload: CuraRecoveryCaptureRequest,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> CuraDeploymentResponse:
    """Queue one named full Cura backup while retaining the closed-Cura safety gate."""

    agent = await session.scalar(
        select(WorkstationAgent).where(WorkstationAgent.id == agent_id).with_for_update()
    )
    if agent is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "workstation_unknown", "Workstation not found")
    if not agent.enabled or agent.capabilities.get("cura_recovery_snapshots") is not True:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_recovery_unavailable",
            "Enable or upgrade the workstation agent before creating a backup",
        )
    installation = next(
        (
            item
            for item in agent.cura_installations
            if isinstance(item, dict) and item.get("installation_id") == payload.installation_id
        ),
        None,
    )
    cura_version = installation.get("version") if installation is not None else None
    if not isinstance(cura_version, str):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_recovery_installation_unknown",
            "Select a currently reported Cura installation",
        )
    now = datetime.now(UTC)
    operation = {
        "operation": "recovery_capture",
        "installation_id": payload.installation_id,
        "cura_version": cura_version,
        "name": payload.name.strip(),
        "description": payload.description.strip() if payload.description else None,
    }
    digest = hashlib.sha256(
        json.dumps(operation, sort_keys=True, separators=(",", ":")).encode("utf-8") + secrets.token_bytes(16)
    ).hexdigest()
    deployment = CuraDeployment(
        agent_id=agent.id,
        material_profile_id=None,
        requested_by=administrator.id,
        status=CuraDeploymentStatus.PENDING,
        payload=operation,
        profile_checksum=digest,
        idempotency_key=f"recovery-capture:{agent.id}:{digest}",
        attempts=0,
        next_attempt_at=now,
        result={},
        created_at=now,
        updated_at=now,
    )
    session.add(deployment)
    await session.flush()
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="cura.recovery_snapshot.request",
        object_type="cura_deployment",
        object_id=deployment.id,
        before=None,
        after={"agent_code": agent.agent_code, "cura_version": cura_version},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return CuraDeploymentResponse.model_validate(deployment)


@router.patch(
    "/workstation-agents/{agent_id}/cura-recovery-snapshots/{snapshot_id}",
    response_model=CuraRecoverySnapshotResponse,
)
async def update_cura_recovery_snapshot(
    agent_id: UUID,
    snapshot_id: UUID,
    payload: CuraRecoverySnapshotUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> CuraRecoverySnapshotResponse:
    """Update the operator-facing name and description of one backup."""

    snapshot = await session.scalar(
        select(CuraRecoverySnapshot)
        .where(CuraRecoverySnapshot.id == snapshot_id, CuraRecoverySnapshot.agent_id == agent_id)
        .with_for_update()
    )
    if snapshot is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "cura_recovery_snapshot_unknown", "Cura recovery point not found"
        )
    if snapshot.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "record_version_conflict", "Recovery point changed; reload")
    before: dict[str, object] = {"name": snapshot.name, "description": snapshot.description}
    if "name" in payload.model_fields_set:
        snapshot.name = payload.name.strip() if payload.name and payload.name.strip() else None
    if "description" in payload.model_fields_set:
        snapshot.description = (
            payload.description.strip() if payload.description and payload.description.strip() else None
        )
    snapshot.record_version += 1
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="cura.recovery_snapshot.update",
        object_type="cura_recovery_snapshot",
        object_id=snapshot.id,
        before=before,
        after={"name": snapshot.name, "description": snapshot.description},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return _recovery_snapshot_response(snapshot)


@router.delete(
    "/workstation-agents/{agent_id}/cura-recovery-snapshots/{snapshot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_cura_recovery_snapshot(
    agent_id: UUID,
    snapshot_id: UUID,
    payload: CuraRecoverySnapshotDelete,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> Response:
    """Delete one explicitly confirmed backup unless a restore still references it."""

    if not payload.confirmed:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "confirmation_required", "Confirm backup deletion"
        )
    snapshot = await session.scalar(
        select(CuraRecoverySnapshot)
        .where(CuraRecoverySnapshot.id == snapshot_id, CuraRecoverySnapshot.agent_id == agent_id)
        .with_for_update()
    )
    if snapshot is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "cura_recovery_snapshot_unknown", "Cura recovery point not found"
        )
    if snapshot.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "record_version_conflict", "Recovery point changed; reload")
    active_restore = await session.scalar(
        select(CuraRecoveryRestore.id).where(
            CuraRecoveryRestore.snapshot_id == snapshot.id,
            CuraRecoveryRestore.status.in_((CuraDeploymentStatus.PENDING, CuraDeploymentStatus.CLAIMED)),
        )
    )
    if active_restore is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_recovery_restore_pending",
            "This backup cannot be deleted while its restore is pending",
        )
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="cura.recovery_snapshot.delete",
        object_type="cura_recovery_snapshot",
        object_id=snapshot.id,
        before={"capture_kind": snapshot.capture_kind, "cura_version": snapshot.cura_version},
        after=None,
        correlation_id=request.state.correlation_id,
    )
    remaining = await session.scalar(
        select(CuraRecoverySnapshot)
        .where(
            CuraRecoverySnapshot.agent_id == agent_id,
            CuraRecoverySnapshot.id != snapshot.id,
        )
        .order_by(CuraRecoverySnapshot.captured_at.desc())
        .limit(1)
    )
    agent = await session.get(WorkstationAgent, agent_id)
    if agent is not None:
        if snapshot.capture_kind == "automatic":
            suppression_key = _recovery_suppression_key(
                snapshot.installation_id,
                snapshot.cura_version,
                snapshot.snapshot_checksum,
            )
            agent.suppressed_recovery_snapshots = list(
                dict.fromkeys([*agent.suppressed_recovery_snapshots, suppression_key])
            )[-100:]
        agent.last_recovery_snapshot_at = remaining.captured_at if remaining is not None else None
        if remaining is None:
            agent.cura_recovery_status = "not_ready"
            agent.cura_recovery_message = "No Cura recovery point is currently retained."
        agent.record_version += 1
    await session.delete(snapshot)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workstation-agents/{agent_id}/cura-recovery-restores",
    response_model=CuraRecoveryRestoreResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cura_recovery_restore(
    agent_id: UUID,
    payload: CuraRecoveryRestoreRequest,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> CuraRecoveryRestoreResponse:
    """Queue an exact-version restore after explicit Administrator confirmation."""

    if not payload.confirmed:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_recovery_confirmation_required",
            "Confirm the reviewed Cura recovery before continuing",
        )
    agent = await session.scalar(
        select(WorkstationAgent).where(WorkstationAgent.id == agent_id).with_for_update()
    )
    if agent is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "workstation_unknown", "Workstation not found")
    if not agent.enabled:
        raise ApiError(status.HTTP_409_CONFLICT, "workstation_disabled", "Enable the workstation first")
    snapshot = await session.scalar(
        select(CuraRecoverySnapshot).where(
            CuraRecoverySnapshot.id == payload.snapshot_id,
            CuraRecoverySnapshot.agent_id == agent.id,
        )
    )
    if snapshot is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "cura_recovery_snapshot_unknown",
            "Cura recovery point not found",
        )
    if _reported_cura_installation(agent, snapshot.installation_id, snapshot.cura_version) is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_recovery_version_mismatch",
            "The recovery point requires the same Cura version on this workstation",
        )
    active_restore = await session.scalar(
        select(CuraRecoveryRestore.id).where(
            CuraRecoveryRestore.agent_id == agent.id,
            CuraRecoveryRestore.status.in_((CuraDeploymentStatus.PENDING, CuraDeploymentStatus.CLAIMED)),
        )
    )
    if active_restore is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_recovery_already_pending",
            "A Cura recovery is already pending for this workstation",
        )
    now = datetime.now(UTC)
    restore = CuraRecoveryRestore(
        agent_id=agent.id,
        snapshot_id=snapshot.id,
        requested_by=administrator.id,
        installation_id=snapshot.installation_id,
        cura_version=snapshot.cura_version,
        snapshot_checksum=snapshot.snapshot_checksum,
        payload=snapshot.payload,
        status=CuraDeploymentStatus.PENDING,
        attempts=0,
        next_attempt_at=now,
        result={},
        created_at=now,
        updated_at=now,
    )
    session.add(restore)
    await session.flush()
    agent.cura_recovery_status = "restore_pending"
    agent.cura_recovery_message = "Close Cura so the selected recovery point can be restored."
    agent.record_version += 1
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="cura.recovery_restore.queue",
        object_type="cura_recovery_restore",
        object_id=restore.id,
        before=None,
        after={
            "agent_code": agent.agent_code,
            "snapshot_id": str(snapshot.id),
            "cura_version": snapshot.cura_version,
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return CuraRecoveryRestoreResponse.model_validate(restore)


@router.post(
    "/workstation-agents/{agent_id}/cura-takeover",
    response_model=WorkstationAgentResponse,
)
async def complete_cura_takeover(
    agent_id: UUID,
    payload: CuraTakeoverRequest,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> WorkstationAgentResponse:
    """Atomically map selected Cura sources, then enable authoritative sync."""

    if not payload.confirmed:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_takeover_confirmation_required",
            "Confirm the reviewed takeover before continuing",
        )
    agent = await session.scalar(
        select(WorkstationAgent).where(WorkstationAgent.id == agent_id).with_for_update()
    )
    if agent is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "workstation_unknown", "Workstation not found")
    if not agent.enabled:
        raise ApiError(status.HTTP_409_CONFLICT, "workstation_disabled", "Enable the workstation first")
    if agent.cura_management_enabled:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_takeover_complete",
            "This workstation is already synchronized",
        )
    if not agent.cura_installations:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_installation_unavailable",
            "Wait for the workstation agent to report a Cura installation",
        )

    reported_sources = {
        str(source.get("source_id")): source
        for source in agent.cura_materials
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }
    if set(payload.reviewed_source_ids) != set(reported_sources):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_source_catalog_changed",
            "The reported Cura profiles changed; reopen the mapping review and try again",
        )
    requested_source_ids = {mapping.source_id for mapping in payload.mappings}
    unknown_sources = sorted(requested_source_ids - reported_sources.keys())
    if unknown_sources:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cura_source_unavailable",
            "A selected Cura source is no longer reported; refresh and review the mappings",
        )

    template_ids = {mapping.template_id for mapping in payload.mappings}
    templates = list(
        await session.scalars(
            select(MaterialTemplate)
            .where(MaterialTemplate.id.in_(template_ids))
            .order_by(MaterialTemplate.id)
            .with_for_update()
        )
    )
    templates_by_id = {template.id: template for template in templates}
    if len(templates_by_id) != len(template_ids) or any(not template.active for template in templates):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "material_template_unavailable",
            "Every mapping must target an active material template",
        )
    duplicate_mapping = (
        await session.scalar(
            select(CuraTakeoverMapping.id).where(
                CuraTakeoverMapping.agent_id == agent.id,
                (
                    CuraTakeoverMapping.source_id.in_(requested_source_ids)
                    | CuraTakeoverMapping.template_id.in_(template_ids)
                ),
            )
        )
        if payload.mappings
        else None
    )
    if duplicate_mapping is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_source_mapping_exists",
            "A selected source or template was already used for this workstation takeover",
        )

    applied: list[dict[str, object]] = []
    for mapping in payload.mappings:
        template = templates_by_id[mapping.template_id]
        current_revision = await session.scalar(
            select(MaterialTemplateRevision)
            .where(
                MaterialTemplateRevision.material_template_id == template.id,
                MaterialTemplateRevision.status == ProfileStatus.PUBLISHED,
            )
            .order_by(MaterialTemplateRevision.version.desc())
            .limit(1)
        )
        if current_revision is None:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "material_template_settings_unavailable",
                "Every selected template must have current settings",
            )
        source = reported_sources[mapping.source_id]
        source_settings = source.get("settings")
        if not isinstance(source_settings, dict):
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "cura_source_invalid",
                "A selected Cura source has invalid settings",
            )
        try:
            current_settings = MaterialSettingsInput.model_validate(current_revision.settings)
            merged_cura = merge_cura_settings(
                settings_from_template(current_revision.settings),
                source_settings,
            )
            imported_settings = MaterialSettingsInput.model_validate(
                material_settings_from_cura(
                    merged_cura,
                    filament_density_g_cm3=current_settings.filament_density_g_cm3,
                    preferred_build_plate_surface_id=(current_settings.preferred_build_plate_surface_id),
                )
            )
        except ValueError as exc:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "cura_source_invalid",
                str(exc),
            ) from exc
        revision, inherited_profiles = await save_template_settings(
            session,
            template=template,
            settings=imported_settings.model_dump(mode="json"),
        )
        source_kind = str(source.get("source_kind") or "material")
        source_name = str(source.get("name") or "Unnamed Cura source").strip()
        session.add(
            CuraTakeoverMapping(
                agent_id=agent.id,
                source_id=mapping.source_id,
                source_kind=source_kind,
                source_name=source_name,
                template_id=template.id,
                applied_template_revision_id=revision.id,
                created_by=administrator.id,
                created_at=datetime.now(UTC),
            )
        )
        applied.append(
            {
                "source_id": mapping.source_id,
                "template_id": str(template.id),
                "settings_snapshot_id": str(revision.id),
                "linked_profiles_updated": len(inherited_profiles),
            }
        )

    agent.cura_management_enabled = True
    agent.record_version += 1
    try:
        deployments = await queue_cura_library(
            session,
            [agent],
            requested_by=administrator.id,
            force=True,
        )
    except ValueError:
        # A clean canonical library may enter managed mode before its first
        # template is created.  The first direct save queues synchronization.
        deployments = []
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="workstation.cura_takeover.complete",
        object_type="workstation_agent",
        object_id=agent.id,
        before={"cura_management_enabled": False},
        after={
            "cura_management_enabled": True,
            "mapped_source_count": len(applied),
            "ignored_source_count": len(reported_sources) - len(applied),
            "mappings": applied,
            "deployment_count": len(deployments),
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return WorkstationAgentResponse.model_validate(agent)


@router.patch("/workstation-agents/{agent_id}", response_model=WorkstationAgentResponse)
async def update_workstation_agent(
    agent_id: UUID,
    payload: WorkstationAgentUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> WorkstationAgentResponse:
    """Rename or revoke a workstation with optimistic concurrency."""

    agent = await session.scalar(
        select(WorkstationAgent).where(WorkstationAgent.id == agent_id).with_for_update()
    )
    if agent is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "workstation_unknown", "Workstation not found")
    if agent.record_version != payload.expected_version:
        raise ApiError(status.HTTP_409_CONFLICT, "version_conflict", "Workstation was changed elsewhere")
    before = {
        "display_name": agent.display_name,
        "enabled": agent.enabled,
        "cura_management_enabled": agent.cura_management_enabled,
    }
    if payload.display_name is not None:
        agent.display_name = payload.display_name.strip()
    if payload.enabled is not None:
        agent.enabled = payload.enabled
    if payload.cura_management_enabled is not None:
        if payload.cura_management_enabled:
            unmanaged_count = _unmanaged_cura_source_count(agent.capabilities)
            if unmanaged_count:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "cura_takeover_required",
                    "Map selected Cura sources and complete the one-time takeover first",
                )
        agent.cura_management_enabled = payload.cura_management_enabled
        if payload.cura_management_enabled:
            try:
                await queue_cura_library(
                    session,
                    [agent],
                    requested_by=administrator.id,
                    force=True,
                )
            except ValueError as exc:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "cura_library_empty",
                    str(exc),
                ) from exc
    agent.record_version += 1
    add_audit_event(
        session,
        actor_id=administrator.id,
        source="web",
        action="workstation.update",
        object_type="workstation_agent",
        object_id=agent.id,
        before=before,
        after={
            "display_name": agent.display_name,
            "enabled": agent.enabled,
            "cura_management_enabled": agent.cura_management_enabled,
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return WorkstationAgentResponse.model_validate(agent)


@router.post(
    "/profiles/{profile_id}/deployments",
    response_model=list[CuraDeploymentResponse],
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_cura_deployments(
    profile_id: UUID,
    payload: CuraDeploymentCreate,
    request: Request,
    operator: Operator,
    session: DatabaseSession,
) -> list[CuraDeploymentResponse]:
    """Queue the complete desired library after validating a published profile."""

    profile = await session.get(MaterialProfile, profile_id)
    if profile is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "unknown_profile", "Profile not found")
    if profile.status != ProfileStatus.PUBLISHED or not profile.checksum:
        raise ApiError(
            status.HTTP_409_CONFLICT, "profile_unpublished", "Publish the profile before deployment"
        )
    query = select(WorkstationAgent).where(
        WorkstationAgent.enabled.is_(True),
        WorkstationAgent.cura_management_enabled.is_(True),
    )
    if payload.agent_ids is not None:
        if not payload.agent_ids:
            raise ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, "no_workstations", "Select a workstation")
        query = query.where(WorkstationAgent.id.in_(payload.agent_ids))
    agents = list(await session.scalars(query))
    if not agents:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "no_managed_workstations",
            "No active workstations have authoritative Cura management enabled",
        )
    if payload.agent_ids is not None and len(agents) != len(set(payload.agent_ids)):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "workstation_unavailable",
            "A selected workstation is unavailable",
        )
    deployments = await queue_cura_library(session, agents, requested_by=operator.id, force=True)
    add_audit_event(
        session,
        actor_id=operator.id,
        source="web",
        action="cura.deployment.queue",
        object_type="material_profile",
        object_id=profile.id,
        before=None,
        after={
            "workstation_count": len(deployments),
            "library_checksum": deployments[0].profile_checksum,
        },
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return [CuraDeploymentResponse.model_validate(item) for item in deployments]


@router.get("/cura-deployments", response_model=list[CuraDeploymentResponse])
async def list_cura_deployments(_: Viewer, session: DatabaseSession) -> list[CuraDeploymentResponse]:
    """List recent workstation work without exposing full profile payloads."""

    items = await session.scalars(
        select(CuraDeployment).order_by(CuraDeployment.created_at.desc()).limit(250)
    )
    return [CuraDeploymentResponse.model_validate(item) for item in items]


@router.post(
    "/workstation-agent/cura-recovery-restores/claim",
    response_model=CuraRecoveryRestoreClaimResponse | None,
)
async def claim_cura_recovery_restore(
    agent: CurrentWorkstationAgent,
    session: DatabaseSession,
) -> CuraRecoveryRestoreClaimResponse | None:
    """Lease the oldest ready recovery operation to exactly its paired agent."""

    now = datetime.now(UTC)
    restore = await session.scalar(
        select(CuraRecoveryRestore)
        .where(
            CuraRecoveryRestore.agent_id == agent.id,
            CuraRecoveryRestore.next_attempt_at <= now,
            or_(
                CuraRecoveryRestore.status == CuraDeploymentStatus.PENDING,
                (CuraRecoveryRestore.status == CuraDeploymentStatus.CLAIMED)
                & (CuraRecoveryRestore.lease_expires_at < now),
            ),
        )
        .order_by(CuraRecoveryRestore.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    agent.last_seen_at = now
    if restore is None:
        await session.commit()
        return None
    restore.status = CuraDeploymentStatus.CLAIMED
    restore.claimed_at = now
    restore.lease_expires_at = now + CLAIM_LEASE
    restore.attempts += 1
    restore.updated_at = now
    agent.cura_recovery_status = "restoring"
    agent.cura_recovery_message = "Cura recovery is being applied while Cura is closed."
    await session.commit()
    return CuraRecoveryRestoreClaimResponse(
        restore_id=restore.id,
        snapshot_checksum=restore.snapshot_checksum,
        payload=restore.payload,
        lease_expires_at=restore.lease_expires_at,
    )


@router.post(
    "/workstation-agent/cura-recovery-restores/{restore_id}/complete",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def complete_cura_recovery_restore(
    restore_id: UUID,
    payload: CuraRecoveryRestoreCompletion,
    request: Request,
    agent: CurrentWorkstationAgent,
    session: DatabaseSession,
) -> Response:
    """Acknowledge a restore without accepting paths or local exception text."""

    restore = await session.scalar(
        select(CuraRecoveryRestore).where(CuraRecoveryRestore.id == restore_id).with_for_update()
    )
    if restore is None or restore.agent_id != agent.id:
        raise ApiError(status.HTTP_404_NOT_FOUND, "cura_recovery_unknown", "Cura recovery not found")
    if restore.status != CuraDeploymentStatus.CLAIMED:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "cura_recovery_not_claimed",
            "Cura recovery is not currently claimed",
        )
    now = datetime.now(UTC)
    restore.result = payload.result.model_dump(mode="json") if payload.result else {}
    restore.lease_expires_at = None
    restore.updated_at = now
    if payload.outcome == "deferred":
        restore.status = CuraDeploymentStatus.PENDING
        restore.next_attempt_at = now + timedelta(seconds=payload.retry_after_seconds)
        restore.last_error_class = "CuraRunning"
        restore.last_error_message = "Cura is open; recovery will retry automatically after it closes."
        agent.cura_recovery_status = "restore_pending"
        agent.cura_recovery_message = "Close Cura so the selected recovery point can be restored."
    elif payload.outcome == "succeeded":
        if payload.result is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "cura_recovery_result_required",
                "A successful Cura recovery requires a bounded result",
            )
        restore.status = CuraDeploymentStatus.SUCCEEDED
        restore.completed_at = now
        restore.last_error_class = None
        restore.last_error_message = None
        agent.cura_recovery_status = "ready"
        agent.cura_recovery_message = None
        agent.last_recovery_restore_at = now
        if agent.cura_management_enabled:
            printers = list(await session.scalars(select(Printer).order_by(Printer.id)))
            for printer in printers:
                await queue_cura_nozzle_update(
                    session,
                    printer=printer,
                    previous_diameter_mm=None,
                    requested_by=restore.requested_by,
                    agents=[agent],
                    force=True,
                    trigger_key=f"recovery-{restore.id}",
                )
            try:
                await queue_cura_library(
                    session,
                    [agent],
                    requested_by=restore.requested_by,
                    force=True,
                )
            except ValueError:
                pass
    else:
        restore.status = CuraDeploymentStatus.FAILED
        restore.completed_at = now
        restore.last_error_class = "CuraRecoveryFailed"
        restore.last_error_message = (
            "Cura recovery failed on the workstation. Review the local agent log and retry."
        )
        agent.cura_recovery_status = "restore_failed"
        agent.cura_recovery_message = restore.last_error_message
    agent.last_seen_at = now
    agent.record_version += 1
    add_audit_event(
        session,
        actor_id=None,
        source="workstation_agent",
        action=f"cura.recovery_restore.{payload.outcome}",
        object_type="cura_recovery_restore",
        object_id=restore.id,
        before={"status": "claimed"},
        after={"status": restore.status.value, "agent_code": agent.agent_code},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/workstation-agent/deployments/claim", response_model=CuraDeploymentClaimResponse | None)
async def claim_cura_deployment(
    agent: CurrentWorkstationAgent,
    session: DatabaseSession,
) -> CuraDeploymentClaimResponse | None:
    """Lease the oldest ready deployment to exactly one agent process."""

    now = datetime.now(UTC)
    deployment = await session.scalar(
        select(CuraDeployment)
        .where(
            CuraDeployment.agent_id == agent.id,
            CuraDeployment.next_attempt_at <= now,
            or_(
                CuraDeployment.status == CuraDeploymentStatus.PENDING,
                (CuraDeployment.status == CuraDeploymentStatus.CLAIMED)
                & (CuraDeployment.lease_expires_at < now),
            ),
        )
        .order_by(CuraDeployment.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    agent.last_seen_at = now
    if deployment is None:
        await session.commit()
        return None
    deployment.status = CuraDeploymentStatus.CLAIMED
    deployment.claimed_at = now
    deployment.lease_expires_at = now + CLAIM_LEASE
    deployment.attempts += 1
    deployment.updated_at = now
    await session.commit()
    return CuraDeploymentClaimResponse(
        deployment_id=deployment.id,
        profile_checksum=deployment.profile_checksum,
        payload=deployment.payload,
        lease_expires_at=deployment.lease_expires_at,
    )


@router.post(
    "/workstation-agent/deployments/{deployment_id}/complete", status_code=status.HTTP_204_NO_CONTENT
)
async def complete_cura_deployment(
    deployment_id: UUID,
    payload: CuraDeploymentCompletion,
    request: Request,
    agent: CurrentWorkstationAgent,
    session: DatabaseSession,
) -> Response:
    """Acknowledge a leased deployment, including safe automatic deferral."""

    _bounded_json(payload.result)
    deployment = await session.scalar(
        select(CuraDeployment).where(CuraDeployment.id == deployment_id).with_for_update()
    )
    if deployment is None or deployment.agent_id != agent.id:
        raise ApiError(status.HTTP_404_NOT_FOUND, "deployment_unknown", "Deployment not found")
    if deployment.status != CuraDeploymentStatus.CLAIMED:
        raise ApiError(
            status.HTTP_409_CONFLICT, "deployment_not_claimed", "Deployment is not currently claimed"
        )
    now = datetime.now(UTC)
    deployment.result = payload.result
    deployment.last_error_class = payload.error_class
    deployment.last_error_message = payload.error_message
    deployment.lease_expires_at = None
    deployment.updated_at = now
    if payload.outcome == "deferred":
        deployment.status = CuraDeploymentStatus.PENDING
        deployment.next_attempt_at = now + timedelta(seconds=payload.retry_after_seconds)
    elif payload.outcome == "succeeded":
        deployment.status = CuraDeploymentStatus.SUCCEEDED
        deployment.completed_at = now
        if deployment.payload.get("operation") is None:
            # A complete current-library install proves older failed desired
            # states for this workstation are obsolete. Retain them as
            # cancelled history without leaving permanent active alerts.
            await session.execute(
                update(CuraDeployment)
                .where(
                    CuraDeployment.id != deployment.id,
                    CuraDeployment.agent_id == agent.id,
                    CuraDeployment.status == CuraDeploymentStatus.FAILED,
                    CuraDeployment.payload["operation"].as_string().is_(None),
                )
                .values(
                    status=CuraDeploymentStatus.CANCELLED,
                    completed_at=now,
                    updated_at=now,
                )
            )
        if deployment.payload.get("operation") == "nozzle_update" and agent.cura_management_enabled:
            try:
                await queue_cura_library(
                    session,
                    [agent],
                    requested_by=deployment.requested_by,
                    force=True,
                )
            except ValueError:
                pass
    else:
        deployment.status = CuraDeploymentStatus.FAILED
        deployment.completed_at = now
    agent.last_seen_at = now
    agent.last_error = payload.error_message if payload.outcome == "failed" else None
    add_audit_event(
        session,
        actor_id=None,
        source="workstation_agent",
        action=f"cura.deployment.{payload.outcome}",
        object_type="cura_deployment",
        object_id=deployment.id,
        before={"status": "claimed"},
        after={"status": deployment.status.value, "agent_code": agent.agent_code},
        correlation_id=request.state.correlation_id,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
