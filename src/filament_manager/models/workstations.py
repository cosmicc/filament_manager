"""Cross-platform Cura workstation agent and deployment models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import CuraDeploymentStatus


class WorkstationPairingCode(UUIDPrimaryKeyMixin, Base):
    """Short-lived, single-use secret used to enroll one workstation."""

    __tablename__ = "workstation_pairing_codes"

    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by_agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workstation_agents.id", ondelete="SET NULL")
    )


class WorkstationAgent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A paired outbound-only process running under a workstation user."""

    __tablename__ = "workstation_agents"

    agent_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    architecture: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cura_management_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    capabilities: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    cura_installations: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    cura_materials: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    cura_recovery_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_ready")
    suppressed_recovery_snapshots: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    cura_recovery_message: Mapped[str | None] = mapped_column(String(500))
    last_recovery_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_recovery_restore_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CuraDeployment(UUIDPrimaryKeyMixin, Base):
    """Immutable profile snapshot queued for one paired workstation."""

    __tablename__ = "cura_deployments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_cura_deployment_idempotency"),
        Index("ix_cura_deployment_claim", "agent_id", "status", "next_attempt_at", "created_at"),
    )

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("workstation_agents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    material_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("material_profiles.id", ondelete="RESTRICT")
    )
    requested_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[CuraDeploymentStatus] = mapped_column(
        Enum(CuraDeploymentStatus, name="cura_deployment_status"),
        nullable=False,
        default=CuraDeploymentStatus.PENDING,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    profile_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(192), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    last_error_class: Mapped[str | None] = mapped_column(String(160))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    @property
    def operation(self) -> str:
        """Return one bounded public operation label without exposing payload data."""

        value = self.payload.get("operation")
        return value if isinstance(value, str) and len(value) <= 64 else "material_library"


class CuraRecoverySnapshot(UUIDPrimaryKeyMixin, Base):
    """Sanitized Cura backup with immutable content and editable display metadata."""

    __tablename__ = "cura_recovery_snapshots"
    __table_args__ = (
        Index(
            "uq_cura_recovery_snapshot_automatic_content",
            "agent_id",
            "installation_id",
            "cura_version",
            "snapshot_checksum",
            unique=True,
            postgresql_where=text("capture_request_id IS NULL"),
        ),
        UniqueConstraint(
            "capture_request_id",
            name="uq_cura_recovery_snapshot_capture_request",
        ),
        Index(
            "ix_cura_recovery_snapshot_history",
            "agent_id",
            "installation_id",
            "cura_version",
            "captured_at",
        ),
    )

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("workstation_agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capture_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cura_deployments.id", ondelete="SET NULL")
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    capture_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="automatic")
    name: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    installation_id: Mapped[str] = mapped_column(String(96), nullable=False)
    cura_version: Mapped[str] = mapped_column(String(32), nullable=False)
    setting_version: Mapped[int | None] = mapped_column(Integer)
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    machine_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_profile_count: Mapped[int] = mapped_column(Integer, nullable=False)
    plugin_count: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CuraRecoveryRestore(UUIDPrimaryKeyMixin, Base):
    """Leased request to restore one immutable sanitized Cura snapshot."""

    __tablename__ = "cura_recovery_restores"
    __table_args__ = (
        Index(
            "ix_cura_recovery_restore_claim",
            "agent_id",
            "status",
            "next_attempt_at",
            "created_at",
        ),
    )

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("workstation_agents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cura_recovery_snapshots.id", ondelete="SET NULL"), index=True
    )
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    installation_id: Mapped[str] = mapped_column(String(96), nullable=False)
    cura_version: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[CuraDeploymentStatus] = mapped_column(
        Enum(CuraDeploymentStatus, name="cura_deployment_status"),
        nullable=False,
        default=CuraDeploymentStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    last_error_class: Mapped[str | None] = mapped_column(String(160))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CuraManagedEditReceipt(UUIDPrimaryKeyMixin, Base):
    """Idempotent receipt for one edited, known Filament Manager Cura material."""

    __tablename__ = "cura_managed_edit_receipts"
    __table_args__ = (
        UniqueConstraint(
            "material_guid",
            "content_checksum",
            name="uq_cura_managed_edit_receipt_content",
        ),
        Index("ix_cura_managed_edit_receipt_source", "source_kind", "source_revision_id"),
    )

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("workstation_agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installation_id: Mapped[str] = mapped_column(String(96), nullable=False)
    material_guid: Mapped[str] = mapped_column(String(36), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_profile_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("material_profiles.id", ondelete="SET NULL")
    )
    created_template_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("material_template_revisions.id", ondelete="SET NULL")
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CuraTakeoverMapping(UUIDPrimaryKeyMixin, Base):
    """Immutable record of one source-to-template choice made at takeover."""

    __tablename__ = "cura_takeover_mappings"
    __table_args__ = (
        UniqueConstraint("agent_id", "source_id", name="uq_cura_takeover_mapping_source"),
        UniqueConstraint("agent_id", "template_id", name="uq_cura_takeover_mapping_template"),
        Index("ix_cura_takeover_mapping_agent_created", "agent_id", "created_at"),
    )

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("workstation_agents.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("material_templates.id", ondelete="RESTRICT"), nullable=False
    )
    applied_template_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("material_template_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
