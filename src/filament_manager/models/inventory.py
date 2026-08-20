"""Canonical inventory, printer, plate, and profile models."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from .enums import (
    MeasurementSource,
    MeasurementStatus,
    NozzleStatus,
    PlateCondition,
    PlateStatus,
    PlateSurfaceTexture,
    ProfileStatus,
    SpoolStatus,
)

MASS = Numeric(12, 3)
MONEY = Numeric(12, 2)
MEASUREMENT = Numeric(12, 5)


class Vendor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A filament manufacturer and its aliases."""

    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FilamentColor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A remembered shared solid color or fixed rainbow screen sample."""

    __tablename__ = "filament_colors"

    name: Mapped[str] = mapped_column(String(96), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    color_hex: Mapped[str] = mapped_column(String(6), nullable=False)
    color_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="solid", server_default=text("'solid'")
    )
    color_hexes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FilamentProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A purchasable filament definition shared by physical spools."""

    __tablename__ = "filament_products"
    __table_args__ = (
        UniqueConstraint(
            "vendor_id",
            "material_type",
            "product_name",
            "color_name",
            "diameter_mm",
            name="uq_filament_product_identity",
        ),
        CheckConstraint("diameter_mm > 0", name="diameter_positive"),
        CheckConstraint("density_g_cm3 > 0", name="density_positive"),
    )

    vendor_id: Mapped[UUID | None] = mapped_column(ForeignKey("vendors.id", ondelete="RESTRICT"))
    material_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    filler: Mapped[str | None] = mapped_column(String(96))
    finish: Mapped[str | None] = mapped_column(String(96))
    color_name: Mapped[str] = mapped_column(String(96), nullable=False)
    color_hex: Mapped[str | None] = mapped_column(String(6))
    color_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="solid", server_default=text("'solid'")
    )
    color_hexes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    product_name: Mapped[str | None] = mapped_column(String(160))
    diameter_mm: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    tolerance_mm: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    density_g_cm3: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    nominal_net_mass_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    source_template_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("material_template_revisions.id", ondelete="SET NULL"), index=True
    )
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    vendor: Mapped[Vendor | None] = relationship()


class Spool(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A uniquely labelled physical spool."""

    __tablename__ = "spools"
    __table_args__ = (
        CheckConstraint("nominal_net_mass_g > 0", name="nominal_mass_positive"),
        CheckConstraint("tare_mass_g >= 0", name="tare_nonnegative"),
        CheckConstraint("remaining_mass_effective_g >= 0", name="remaining_nonnegative"),
        Index("ix_spools_status_archived", "status", "archived"),
    )

    spool_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    filament_product_id: Mapped[UUID] = mapped_column(
        ForeignKey("filament_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    nominal_net_mass_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    tare_mass_g: Mapped[Decimal] = mapped_column(MASS, nullable=False, default=Decimal("0"))
    remaining_mass_expected_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    remaining_mass_measured_g: Mapped[Decimal | None] = mapped_column(MASS)
    remaining_mass_effective_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    weight_confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="estimated")
    status: Mapped[SpoolStatus] = mapped_column(
        Enum(SpoolStatus, name="spool_status"), nullable=False, default=SpoolStatus.NEEDS_WEIGHING
    )
    purchase_source: Mapped[str | None] = mapped_column(String(160))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    first_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_measurement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_usage_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(160))
    # Existing Spoolman locations may be adopted once. After this flag is set,
    # Filament Manager owns the free-text location, including an intentional clear.
    location_authoritative: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    active_printer_id: Mapped[UUID | None] = mapped_column(ForeignKey("printers.id"))
    spoolman_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    label_path: Mapped[str | None] = mapped_column(String(512))
    notes: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    filament_product: Mapped[FilamentProduct] = relationship()
    measurements: Mapped[list["SpoolMeasurement"]] = relationship(
        back_populates="spool", order_by="SpoolMeasurement.measured_at.desc()"
    )


class SpoolMeasurement(UUIDPrimaryKeyMixin, Base):
    """An immutable physical gross-weight observation."""

    __tablename__ = "spool_measurements"
    __table_args__ = (
        CheckConstraint("gross_mass_g >= 0", name="gross_nonnegative"),
        CheckConstraint("tare_mass_g >= 0", name="measurement_tare_nonnegative"),
        UniqueConstraint("spool_id", "idempotency_key", name="uq_measurement_idempotency"),
        Index("ix_measurements_spool_time", "spool_id", "measured_at"),
    )

    spool_id: Mapped[UUID] = mapped_column(ForeignKey("spools.id", ondelete="RESTRICT"), nullable=False)
    source: Mapped[MeasurementSource] = mapped_column(
        Enum(MeasurementSource, name="measurement_source"), nullable=False
    )
    status: Mapped[MeasurementStatus] = mapped_column(
        Enum(MeasurementStatus, name="measurement_status"), nullable=False
    )
    gross_mass_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    tare_mass_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    net_mass_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    expected_before_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    variance_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    uncertainty_g: Mapped[Decimal | None] = mapped_column(MASS)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"))
    device_sequence: Mapped[int | None] = mapped_column(Integer)
    operator_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(String(256))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    spool: Mapped[Spool] = relationship(back_populates="measurements")


class SpoolUsageEvent(UUIDPrimaryKeyMixin, Base):
    """An immutable consumption or adjustment event."""

    __tablename__ = "spool_usage_events"
    __table_args__ = (UniqueConstraint("source", "idempotency_key", name="uq_usage_source_key"),)

    spool_id: Mapped[UUID] = mapped_column(ForeignKey("spools.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    printer_id: Mapped[UUID | None] = mapped_column(ForeignKey("printers.id"))
    print_job_id: Mapped[str | None] = mapped_column(String(160))
    mass_delta_g: Mapped[Decimal] = mapped_column(MASS, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Printer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A configured Moonraker/Klipper printer."""

    __tablename__ = "printers"

    printer_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    moonraker_base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    nozzle_diameter_mm: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    build_volume: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    manufacturer: Mapped[str | None] = mapped_column(String(160))
    model: Mapped[str | None] = mapped_column(String(160))
    kinematics: Mapped[str | None] = mapped_column(String(48))
    nozzle_material: Mapped[str | None] = mapped_column(String(96))
    extruder_type: Mapped[str | None] = mapped_column(String(96))
    klipper_version: Mapped[str | None] = mapped_column(String(96))
    moonraker_version: Mapped[str | None] = mapped_column(String(96))
    host_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    last_info_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    print_history_initialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_print_history_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_print_history_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_plate_id: Mapped[UUID | None] = mapped_column(ForeignKey("build_plates.id"))
    active_plate_surface_id: Mapped[UUID | None] = mapped_column(ForeignKey("build_plate_surfaces.id"))
    active_nozzle_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("nozzles.id", ondelete="SET NULL"), unique=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Nozzle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A uniquely identified physical nozzle with immutable print attribution."""

    __tablename__ = "nozzles"
    __table_args__ = (
        CheckConstraint("diameter_mm > 0", name="nozzle_diameter_positive"),
        Index("ix_nozzles_status_code", "status", "nozzle_code"),
    )

    nozzle_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    diameter_mm: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    material: Mapped[str] = mapped_column(String(96), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(160))
    product_name: Mapped[str | None] = mapped_column(String(160))
    coating: Mapped[str | None] = mapped_column(String(96))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[NozzleStatus] = mapped_column(
        Enum(NozzleStatus, name="nozzle_status"), nullable=False, default=NozzleStatus.AVAILABLE
    )
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BuildPlate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A physical P-number build plate that may have two printable sides."""

    __tablename__ = "build_plates"
    __table_args__ = (
        CheckConstraint(
            "plate_code ~ '^P[1-9][0-9]*$'",
            name="build_plate_code_format",
        ),
    )

    plate_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    product_name: Mapped[str | None] = mapped_column(String(160))
    shape: Mapped[str | None] = mapped_column(String(32))
    dimensions_mm: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    magnetic: Mapped[bool | None] = mapped_column(Boolean)
    flexible: Mapped[bool | None] = mapped_column(Boolean)
    condition: Mapped[PlateCondition] = mapped_column(
        Enum(PlateCondition, name="plate_condition"), nullable=False, default=PlateCondition.GOOD
    )
    status: Mapped[PlateStatus] = mapped_column(
        Enum(PlateStatus, name="plate_status"), nullable=False, default=PlateStatus.ACTIVE
    )
    preferred_materials: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    max_bed_temp_c: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    last_cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleaning_due_after_prints: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    cleaning_due_after_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    mesh_due_after_prints: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    mesh_due_after_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    notes: Mapped[str | None] = mapped_column(Text)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    image_media_type: Mapped[str | None] = mapped_column(String(32))
    image_sha256: Mapped[str | None] = mapped_column(String(64))
    image_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    surfaces: Mapped[list["BuildPlateSurface"]] = relationship(
        back_populates="plate",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BuildPlateSurface.side",
    )


class BuildPlateSurface(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One printable side and its exact same-named Moonraker mesh profile."""

    __tablename__ = "build_plate_surfaces"
    __table_args__ = (
        CheckConstraint("side IN ('a', 'b')", name="build_plate_surface_side"),
        CheckConstraint(
            "surface_code ~ '^P[1-9][0-9]*b?$'",
            name="build_plate_surface_code_format",
        ),
        CheckConstraint(
            "klipper_mesh_profile = surface_code",
            name="build_plate_surface_mesh_matches_code",
        ),
        UniqueConstraint("build_plate_id", "side", name="uq_build_plate_surface_side"),
    )

    build_plate_id: Mapped[UUID] = mapped_column(
        ForeignKey("build_plates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    side: Mapped[str] = mapped_column(String(1), nullable=False)
    surface_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    klipper_mesh_profile: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    surface_material: Mapped[str | None] = mapped_column(String(120))
    texture: Mapped[PlateSurfaceTexture | None] = mapped_column(
        Enum(PlateSurfaceTexture, name="plate_surface_texture")
    )
    mesh_available: Mapped[bool | None] = mapped_column(Boolean)
    last_mesh_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_mesh_calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    plate: Mapped[BuildPlate] = relationship(back_populates="surfaces")


class MaterialProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A template-linked override revision with a complete resolved snapshot."""

    __tablename__ = "material_profiles"
    __table_args__ = (
        UniqueConstraint(
            "filament_product_id",
            "printer_id",
            "nozzle_diameter_mm",
            "version",
            name="uq_material_profile_version",
        ),
        UniqueConstraint(
            "source_workstation_agent_id",
            "source_cura_material_id",
            name="uq_material_profiles_cura_source",
        ),
    )

    filament_product_id: Mapped[UUID] = mapped_column(ForeignKey("filament_products.id"), nullable=False)
    printer_id: Mapped[UUID] = mapped_column(ForeignKey("printers.id"), nullable=False)
    nozzle_diameter_mm: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    min_layer_height_mm: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    max_layer_height_mm: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProfileStatus] = mapped_column(Enum(ProfileStatus, name="profile_status"), nullable=False)
    chamber_temp_c: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    extruder_temp_c: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    bed_temp_c: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    flow_percent: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    print_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    outer_wall_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    inner_wall_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    infill_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    top_bottom_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    initial_layer_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    travel_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    support_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    bridge_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    retraction_distance_mm: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    retraction_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    retraction_prime_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    cooling_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cooling_min_percent: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    cooling_max_percent: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    support_overhang_angle_deg: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    tree_max_branch_angle_deg: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    pressure_advance: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    filament_density_g_cm3: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    preferred_build_plate_surface_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("build_plate_surfaces.id")
    )
    # Keep the established database column name for a non-destructive upgrade,
    # but treat the relationship as the active inherited base, not provenance.
    base_template_revision_id: Mapped[UUID] = mapped_column(
        "source_template_revision_id",
        ForeignKey("material_template_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    setting_overrides: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    source_workstation_agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "workstation_agents.id",
            name="fk_material_profiles_cura_source_agent",
            ondelete="SET NULL",
        ),
        index=True,
    )
    source_cura_material_id: Mapped[str | None] = mapped_column(String(64))
    ironing_enabled: Mapped[bool | None] = mapped_column(Boolean)
    ironing_flow_percent: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    ironing_speed_mm_s: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    ironing_line_spacing_mm: Mapped[Decimal | None] = mapped_column(MEASUREMENT)
    cura_extensions_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cura_extensions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    checksum: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MaterialTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reusable material family scoped to one printer and nozzle."""

    __tablename__ = "material_templates"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    material_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    printer_id: Mapped[UUID] = mapped_column(
        ForeignKey("printers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    nozzle_diameter_mm: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    filament_diameter_mm: Mapped[Decimal] = mapped_column(MEASUREMENT, nullable=False)
    source_workstation_agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "workstation_agents.id",
            name="fk_material_templates_cura_source_agent",
            ondelete="SET NULL",
        ),
        index=True,
    )
    source_cura_material_id: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (
        Index(
            "uq_material_template_manual_scope",
            func.lower(material_type),
            printer_id,
            nozzle_diameter_mm,
            unique=True,
            postgresql_where=source_cura_material_id.is_(None),
        ),
        UniqueConstraint(
            "source_workstation_agent_id",
            "source_cura_material_id",
            name="uq_material_template_cura_source",
        ),
    )


class MaterialTemplateRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An immutable material-template settings snapshot."""

    __tablename__ = "material_template_revisions"
    __table_args__ = (
        UniqueConstraint(
            "material_template_id",
            "version",
            name="uq_material_template_revision_version",
        ),
    )

    material_template_id: Mapped[UUID] = mapped_column(
        ForeignKey("material_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProfileStatus] = mapped_column(Enum(ProfileStatus, name="profile_status"), nullable=False)
    settings: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
