"""Canonical print history, material segments, and quality assessments."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import GcodeInspectionStatus, PrintJobStatus, PrintQualityRating

PRINT_MEASUREMENT = Numeric(14, 5)
PRINT_DURATION = Numeric(14, 3)


class PrintJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One Moonraker print with the exact canonical state captured at its start."""

    __tablename__ = "print_jobs"
    __table_args__ = (
        UniqueConstraint("printer_id", "moonraker_job_id", name="uq_print_job_moonraker"),
        Index("ix_print_jobs_started_at", "started_at"),
        Index("ix_print_jobs_profile_status", "material_profile_id", "status"),
    )

    printer_id: Mapped[UUID] = mapped_column(
        ForeignKey("printers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    moonraker_job_id: Mapped[str | None] = mapped_column(String(160))
    moonraker_file_uuid: Mapped[str | None] = mapped_column(String(96))
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    gcode_sha256: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="live")
    status: Mapped[PrintJobStatus] = mapped_column(
        Enum(PrintJobStatus, name="print_job_status"), nullable=False
    )

    spool_id: Mapped[UUID | None] = mapped_column(ForeignKey("spools.id", ondelete="SET NULL"))
    filament_product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("filament_products.id", ondelete="SET NULL")
    )
    material_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("material_profiles.id", ondelete="SET NULL"), index=True
    )
    material_profile_version: Mapped[int | None] = mapped_column(Integer)
    build_plate_id: Mapped[UUID | None] = mapped_column(ForeignKey("build_plates.id", ondelete="SET NULL"))
    build_plate_surface_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("build_plate_surfaces.id", ondelete="SET NULL")
    )
    nozzle_diameter_mm: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    material_guid: Mapped[str | None] = mapped_column(String(96))
    material_name: Mapped[str | None] = mapped_column(String(255))
    material_type: Mapped[str | None] = mapped_column(String(96))
    state_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    profile_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    inspection_status: Mapped[GcodeInspectionStatus] = mapped_column(
        Enum(GcodeInspectionStatus, name="gcode_inspection_status"),
        nullable=False,
        default=GcodeInspectionStatus.PENDING,
    )
    inspection_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="warn")
    inspection: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    slicer: Mapped[str | None] = mapped_column(String(96))
    slicer_version: Mapped[str | None] = mapped_column(String(96))
    cura_quality_profile: Mapped[str | None] = mapped_column(String(255))
    layer_height_mm: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    line_width_mm: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    extruder_temp_c: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    bed_temp_c: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    chamber_temp_c: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    print_speed_mm_s: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    pressure_advance: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    retraction_distance_mm: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    retraction_speed_mm_s: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    flow_percent: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    predicted_filament_length_mm: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    predicted_filament_weight_g: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    actual_filament_length_mm: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    actual_filament_weight_g: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    estimated_duration_seconds: Mapped[Decimal | None] = mapped_column(PRINT_DURATION)
    print_duration_seconds: Mapped[Decimal | None] = mapped_column(PRINT_DURATION)
    total_duration_seconds: Mapped[Decimal | None] = mapped_column(PRINT_DURATION)
    support_configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    machine_name: Mapped[str | None] = mapped_column(String(255))
    timelapse_url: Mapped[str | None] = mapped_column(String(1024))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    segments: Mapped[list["PrintMaterialSegment"]] = relationship(
        back_populates="print_job", order_by="PrintMaterialSegment.started_at", lazy="selectin"
    )
    assessments: Mapped[list["PrintAssessment"]] = relationship(
        back_populates="print_job", order_by="PrintAssessment.revision", lazy="selectin"
    )


class PrintMaterialSegment(UUIDPrimaryKeyMixin, Base):
    """A bounded spool/profile interval within a print, including M600 changes."""

    __tablename__ = "print_material_segments"
    __table_args__ = (
        UniqueConstraint("print_job_id", "segment_number", name="uq_print_material_segment_number"),
        Index("ix_print_segments_spool_time", "spool_id", "started_at"),
    )

    print_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False
    )
    segment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    spool_id: Mapped[UUID | None] = mapped_column(ForeignKey("spools.id", ondelete="SET NULL"))
    filament_product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("filament_products.id", ondelete="SET NULL")
    )
    material_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("material_profiles.id", ondelete="SET NULL")
    )
    material_profile_version: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    state_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_filament_length_mm: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    actual_filament_weight_g: Mapped[Decimal | None] = mapped_column(PRINT_MEASUREMENT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    print_job: Mapped[PrintJob] = relationship(back_populates="segments")


class PrintAssessment(UUIDPrimaryKeyMixin, Base):
    """One immutable revision of a human print-quality assessment."""

    __tablename__ = "print_assessments"
    __table_args__ = (
        UniqueConstraint("print_job_id", "revision", name="uq_print_assessment_revision"),
        Index("ix_print_assessments_job_created", "print_job_id", "created_at"),
    )

    print_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[PrintQualityRating] = mapped_column(
        Enum(PrintQualityRating, name="print_quality_rating"), nullable=False
    )
    defect_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("print_assessments.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    print_job: Mapped[PrintJob] = relationship(back_populates="assessments")
