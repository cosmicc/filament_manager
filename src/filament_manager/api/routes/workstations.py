"""Secure workstation enrollment and leased Cura profile deployment APIs."""

import json
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import or_, select

from filament_manager.config import get_settings
from filament_manager.models.enums import CuraDeploymentStatus, ProfileStatus
from filament_manager.models.inventory import (
    MaterialProfile,
    MaterialTemplate,
    MaterialTemplateRevision,
)
from filament_manager.models.workstations import CuraDeployment, WorkstationAgent, WorkstationPairingCode
from filament_manager.security import create_agent_token, create_pairing_code, hash_token
from filament_manager.services.cura_edits import import_managed_cura_edits
from filament_manager.services.cura_library import build_cura_library, queue_cura_library
from filament_manager.services.events import add_audit_event

from ..dependencies import Administrator, CurrentWorkstationAgent, DatabaseSession, Operator, Viewer
from ..errors import ApiError
from ..schemas import (
    CuraDeploymentClaimResponse,
    CuraDeploymentCompletion,
    CuraDeploymentCreate,
    CuraDeploymentResponse,
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


def _bounded_json(value: object) -> None:
    """Reject oversized agent metadata before it reaches PostgreSQL or audit logs."""

    if len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8")) > MAX_AGENT_JSON_BYTES:
        raise ApiError(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "agent_metadata_too_large",
            "Agent metadata is too large",
        )


def _public_pairing_transport_is_safe() -> bool:
    """Require the configured public URL to use TLS except for loopback development."""

    parsed = urlparse(str(get_settings().app.base_url))
    return parsed.scheme == "https" or parsed.hostname in {"localhost", "127.0.0.1", "::1"}


async def _has_unpublished_cura_template_imports(
    session: DatabaseSession,
    agent_id: UUID,
) -> bool:
    """Return whether imported Cura material content is not yet in the desired library."""

    template_id = await session.scalar(
        select(MaterialTemplate.id).where(
            MaterialTemplate.source_workstation_agent_id == agent_id,
            or_(
                MaterialTemplate.active.is_(False),
                ~select(MaterialTemplateRevision.id)
                .where(
                    MaterialTemplateRevision.material_template_id == MaterialTemplate.id,
                    MaterialTemplateRevision.status == ProfileStatus.PUBLISHED,
                )
                .exists(),
            ),
        )
    )
    return template_id is not None


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
            bool(payload.cura_installations) and payload.capabilities.get("unmanaged_material_count") == 0
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
    agent.last_error = payload.last_error
    if (
        not agent.cura_management_enabled
        and payload.cura_installations
        and payload.capabilities.get("unmanaged_material_count") == 0
        and not await _has_unpublished_cura_template_imports(session, agent.id)
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
            # never hide Cura materials until something has been published.
            pass
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workstation-agents", response_model=list[WorkstationAgentResponse])
async def list_workstation_agents(_: Viewer, session: DatabaseSession) -> list[WorkstationAgentResponse]:
    """List paired workstations without credential material."""

    agents = await session.scalars(select(WorkstationAgent).order_by(WorkstationAgent.display_name))
    return [WorkstationAgentResponse.model_validate(agent) for agent in agents]


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
            if await _has_unpublished_cura_template_imports(session, agent.id):
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "cura_template_imports_unpublished",
                    "Review and publish every imported Cura template before managing this workstation",
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
