"""Calibration session and ordered step models."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import CalibrationStatus, CalibrationStepStatus


class CalibrationSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A resumable calibration run for one product, printer, nozzle, and plate."""

    __tablename__ = "calibration_sessions"

    filament_product_id: Mapped[UUID] = mapped_column(ForeignKey("filament_products.id"), nullable=False)
    spool_id: Mapped[UUID | None] = mapped_column(ForeignKey("spools.id"))
    printer_id: Mapped[UUID] = mapped_column(ForeignKey("printers.id"), nullable=False)
    nozzle_diameter_mm: Mapped[Decimal] = mapped_column(Numeric(12, 5), nullable=False)
    build_plate_id: Mapped[UUID | None] = mapped_column(ForeignKey("build_plates.id"))
    build_plate_surface_id: Mapped[UUID | None] = mapped_column(ForeignKey("build_plate_surfaces.id"))
    baseline_profile_id: Mapped[UUID | None] = mapped_column(ForeignKey("material_profiles.id"))
    published_profile_id: Mapped[UUID | None] = mapped_column(ForeignKey("material_profiles.id"))
    target_layer_height_mm: Mapped[Decimal | None] = mapped_column(Numeric(12, 5))
    status: Mapped[CalibrationStatus] = mapped_column(
        Enum(CalibrationStatus, name="calibration_status"), nullable=False
    )
    operator_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    override_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    steps: Mapped[list["CalibrationStep"]] = relationship(
        back_populates="session", order_by="CalibrationStep.step_order", cascade="all, delete-orphan"
    )


class CalibrationStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One ordered test and its selected result."""

    __tablename__ = "calibration_steps"
    __table_args__ = (
        UniqueConstraint("session_id", "step_key", name="uq_calibration_step_key"),
        UniqueConstraint("session_id", "step_order", name="uq_calibration_step_order"),
    )

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("calibration_sessions.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[CalibrationStepStatus] = mapped_column(
        Enum(CalibrationStepStatus, name="calibration_step_status"), nullable=False
    )
    inputs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    artifact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    affected_profile_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    session: Mapped[CalibrationSession] = relationship(back_populates="steps")
