"""Outbox, audit, projection, import, and future-device models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import JobStatus, NotificationSeverity, PlateMaintenanceType


class OutboxJob(UUIDPrimaryKeyMixin, Base):
    """Durable work created in the same transaction as canonical changes."""

    __tablename__ = "outbox_jobs"
    __table_args__ = (
        UniqueConstraint("job_type", "idempotency_key", name="uq_outbox_type_key"),
        Index("ix_outbox_claim", "status", "next_attempt_at", "created_at"),
    )

    job_type: Mapped[str] = mapped_column(String(96), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    aggregate_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_class: Mapped[str | None] = mapped_column(String(160))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remote_fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only security and business audit event."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_object_time", "object_type", "object_id", "occurred_at"),)

    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(48), nullable=False)
    action: Mapped[str] = mapped_column(String(96), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[UUID | None]
    before: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectionState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Last acknowledged state for a canonical record in an external system."""

    __tablename__ = "projection_states"
    __table_args__ = (UniqueConstraint("system", "object_type", "object_id", name="uq_projection_object"),)

    system: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[UUID] = mapped_column(nullable=False)
    remote_id: Mapped[str | None] = mapped_column(String(160))
    remote_fingerprint: Mapped[str | None] = mapped_column(String(64))
    acknowledged_version: Mapped[int | None] = mapped_column(Integer)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))


class Device(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Registered future scale or NFC adapter."""

    __tablename__ = "devices"

    device_code: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    device_type: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    location: Mapped[str | None] = mapped_column(String(160))
    firmware_version: Mapped[str | None] = mapped_column(String(96))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_sequence: Mapped[int | None] = mapped_column(Integer)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NfcTag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audited identifier mapping for a spool NFC tag."""

    __tablename__ = "nfc_tags"

    tag_uid_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    spool_id: Mapped[UUID] = mapped_column(ForeignKey("spools.id"), nullable=False)
    technology: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRun(UUIDPrimaryKeyMixin, Base):
    """A workbook dry-run or approved commit report."""

    __tablename__ = "import_runs"

    source_name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    report: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    approved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class ApplicationSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned server-owned operational setting edited only by administrators."""

    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class BuildPlateMaintenanceEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only plate cleaning or side-specific mesh-calibration record."""

    __tablename__ = "build_plate_maintenance_events"
    __table_args__ = (Index("ix_plate_maintenance_plate_time", "build_plate_id", "occurred_at"),)

    build_plate_id: Mapped[UUID] = mapped_column(
        ForeignKey("build_plates.id", ondelete="RESTRICT"), nullable=False
    )
    build_plate_surface_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("build_plate_surfaces.id", ondelete="RESTRICT")
    )
    maintenance_type: Mapped[PlateMaintenanceType] = mapped_column(
        Enum(PlateMaintenanceType, name="plate_maintenance_type"), nullable=False
    )
    performed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="web")
    notes: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NozzleLifecycleEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only installation, removal, and retirement history for a physical nozzle."""

    __tablename__ = "nozzle_lifecycle_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('installed', 'removed', 'retired', 'reactivated')",
            name="event_type",
        ),
        Index("ix_nozzle_lifecycle_time", "nozzle_id", "occurred_at"),
    )

    nozzle_id: Mapped[UUID] = mapped_column(ForeignKey("nozzles.id", ondelete="RESTRICT"), nullable=False)
    printer_id: Mapped[UUID | None] = mapped_column(ForeignKey("printers.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    performed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="web")
    notes: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DiagnosticRun(UUIDPrimaryKeyMixin, Base):
    """Immutable result from an Administrator-triggered recovery validation."""

    __tablename__ = "diagnostic_runs"
    __table_args__ = (Index("ix_diagnostic_runs_started", "started_at"),)

    run_type: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    results: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerHeartbeat(UUIDPrimaryKeyMixin, Base):
    """Ephemeral, secret-free liveness record for one scheduler or dispatcher."""

    __tablename__ = "worker_heartbeats"
    __table_args__ = (Index("ix_worker_heartbeats_seen", "last_seen_at"),)

    worker_id: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    worker_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_job_id: Mapped[UUID | None]
    current_job_type: Mapped[str | None] = mapped_column(String(96))
    last_error_class: Mapped[str | None] = mapped_column(String(160))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Notification(UUIDPrimaryKeyMixin, Base):
    """Deduplicated operator event retained independently of structured logs."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_active_time", "active", "last_seen_at"),)

    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[NotificationSeverity] = mapped_column(
        Enum(NotificationSeverity, name="notification_severity"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    action_path: Mapped[str | None] = mapped_column(String(255))
    object_type: Mapped[str | None] = mapped_column(String(64))
    object_id: Mapped[UUID | None]
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserNotificationState(Base):
    """Per-user read state for a shared notification event."""

    __tablename__ = "user_notification_states"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
