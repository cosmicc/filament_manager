"""Pydantic API contracts kept separate from ORM models."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from filament_manager.domain.cura_material_settings import (
    CURA_EXTENSION_SETTING_KEYS,
    CURA_MATERIAL_SETTINGS,
    cura_settings_for_profile,
)
from filament_manager.models.enums import (
    CalibrationStatus,
    CalibrationStepStatus,
    CuraDeploymentStatus,
    GcodeInspectionStatus,
    MeasurementSource,
    NotificationSeverity,
    NozzleStatus,
    PlateMaintenanceType,
    PlateSurfaceTexture,
    PrintJobStatus,
    PrintQualityRating,
    ProfileStatus,
    UserRole,
)


class ApiModel(BaseModel):
    """Shared API model configuration."""

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(ApiModel):
    code: str
    message: str
    correlation_id: str | None = None


class LoginRequest(ApiModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(ApiModel):
    id: UUID
    username: str
    display_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    record_version: int


class LoginResponse(ApiModel):
    user: UserResponse


class UserCreate(ApiModel):
    username: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=256)
    role: UserRole


class UserUpdate(ApiModel):
    """Administrator-managed account identity, role, and activation state."""

    expected_version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None


class UserPasswordReset(ApiModel):
    """Administrator-set temporary password requiring replacement at sign-in."""

    expected_version: int = Field(ge=1)
    temporary_password: str = Field(min_length=10, max_length=256)


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class VendorCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    preferred: bool = False
    notes: str | None = Field(default=None, max_length=2000)


ColorHex = Annotated[str, Field(pattern=r"^#?[0-9A-Fa-f]{6}$")]


class FilamentCreate(ApiModel):
    vendor_id: UUID | None = None
    material_type: str = Field(min_length=1, max_length=48)
    filler: str | None = Field(default=None, max_length=96)
    finish: str | None = Field(default=None, max_length=96)
    color_name: str = Field(min_length=1, max_length=96)
    color_hex: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")
    color_mode: Literal["solid", "multicolor", "rainbow"] = "solid"
    color_hexes: list[ColorHex] = Field(default_factory=list, max_length=6)
    product_name: str | None = Field(default=None, max_length=160)
    diameter_mm: Decimal = Field(gt=0)
    tolerance_mm: Decimal | None = Field(default=None, ge=0)
    density_g_cm3: Decimal = Field(gt=0)
    nominal_net_mass_g: Decimal = Field(gt=0)
    notes: str | None = Field(default=None, max_length=4000)
    material_template_revision_id: UUID | None = None


class FilamentResponse(FilamentCreate):
    id: UUID
    vendor_name: str | None = None
    archived: bool = False
    color_editable: bool = True
    record_version: int


class FilamentUpdate(ApiModel):
    """Editable product metadata with global color-sample semantics."""

    expected_version: int = Field(ge=1)
    vendor_id: UUID | None = None
    material_type: str | None = Field(default=None, min_length=1, max_length=48)
    filler: str | None = Field(default=None, max_length=96)
    finish: str | None = Field(default=None, max_length=96)
    color_name: str | None = Field(default=None, min_length=1, max_length=96)
    color_hex: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")
    color_mode: Literal["solid", "multicolor", "rainbow"] | None = None
    color_hexes: list[ColorHex] | None = Field(default=None, max_length=6)
    product_name: str | None = Field(default=None, max_length=160)
    diameter_mm: Decimal | None = Field(default=None, gt=0)
    tolerance_mm: Decimal | None = Field(default=None, ge=0)
    density_g_cm3: Decimal | None = Field(default=None, gt=0)
    nominal_net_mass_g: Decimal | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=4000)
    material_template_revision_id: UUID | None = None
    archived: bool | None = None


class FilamentColorResponse(ApiModel):
    """A remembered color-name mapping used by every matching product."""

    id: UUID
    name: str
    normalized_name: str
    color_hex: str
    color_mode: Literal["solid", "multicolor", "rainbow"]
    color_hexes: list[str]
    record_version: int


class SpoolCreate(ApiModel):
    spool_code: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=64)
    filament_product_id: UUID
    nominal_net_mass_g: Decimal = Field(gt=0)
    tare_mass_g: Decimal | None = Field(
        default=None,
        ge=0,
        description=(
            "Optional known empty-spool mass. When omitted with a full-spool scale weight, "
            "Filament Manager infers it from gross mass minus the entered filament amount."
        ),
    )
    initial_gross_mass_g: Decimal | None = Field(default=None, ge=0)
    purchase_source: str | None = Field(default=None, max_length=160)
    purchase_date: date | None = None
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    location: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("location")
    @classmethod
    def normalize_location(cls, value: str | None) -> str | None:
        """Store bucket labels without accidental surrounding whitespace."""

        if value is None:
            return None
        return value.strip() or None


class SpoolUpdate(ApiModel):
    expected_version: int = Field(ge=1)
    spool_code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$", max_length=64)
    filament_product_id: UUID | None = None
    nominal_net_mass_g: Decimal | None = Field(default=None, gt=0)
    tare_mass_g: Decimal | None = Field(default=None, ge=0)
    remaining_mass_g: Decimal | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=160)
    purchase_source: str | None = Field(default=None, max_length=160)
    purchase_date: date | None = None
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    notes: str | None = Field(default=None, max_length=4000)
    archived: bool | None = None

    @field_validator("location")
    @classmethod
    def normalize_location(cls, value: str | None) -> str | None:
        """Treat a blank submitted bucket as an intentional location clear."""

        if value is None:
            return None
        return value.strip() or None


class SpoolResponse(ApiModel):
    id: UUID
    spool_code: str
    filament_product_id: UUID
    material_type: str
    filler: str | None
    finish: str | None
    color_name: str
    color_hex: str | None
    color_mode: Literal["solid", "multicolor", "rainbow"]
    color_hexes: list[str]
    vendor_name: str | None
    product_name: str | None
    nominal_net_mass_g: Decimal
    tare_mass_g: Decimal
    remaining_mass_expected_g: Decimal
    remaining_mass_measured_g: Decimal | None
    remaining_mass_effective_g: Decimal
    remaining_percent: Decimal
    weight_confidence: str
    status: str
    purchase_source: str | None
    purchase_date: date | None
    purchase_cost: Decimal | None
    currency: str
    location: str | None
    spoolman_id: int | None
    active_printer_id: UUID | None
    last_measurement_at: datetime | None
    notes: str | None
    archived: bool
    record_version: int
    completed_print_count: int = 0


class MeasurementCreate(ApiModel):
    gross_mass_g: Decimal = Field(ge=0)
    tare_mass_g: Decimal | None = Field(
        default=None,
        gt=0,
        description=(
            "Required only when the stored tare is unknown; established atomically with the measurement"
        ),
    )
    source: MeasurementSource = MeasurementSource.MANUAL
    measured_at: datetime | None = None
    confirmed: bool = False
    allow_above_nominal: bool = False
    notes: str | None = Field(default=None, max_length=4000)


class MeasurementResponse(ApiModel):
    id: UUID
    spool_id: UUID
    source: MeasurementSource
    status: str
    gross_mass_g: Decimal
    tare_mass_g: Decimal
    net_mass_g: Decimal
    expected_before_g: Decimal
    variance_g: Decimal
    requires_confirmation: bool
    confirmed: bool
    measured_at: datetime


class BuildPlateSurfaceResponse(ApiModel):
    """One printable plate side and its matching Moonraker mesh."""

    id: UUID
    build_plate_id: UUID
    side: str
    surface_code: str
    klipper_mesh_profile: str
    surface_material: str | None
    texture: PlateSurfaceTexture | None
    mesh_available: bool | None
    last_mesh_checked_at: datetime | None
    last_mesh_calibrated_at: datetime | None
    notes: str | None
    record_version: int
    completed_print_count: int = 0


class BuildPlateSurfaceCreate(ApiModel):
    """Optional metadata used when an Operator adds the physical Side B."""

    surface_material: str | None = Field(default=None, max_length=120)
    texture: PlateSurfaceTexture | None = None
    notes: str | None = Field(default=None, max_length=4000)


class BuildPlateDimensions(ApiModel):
    """Optional physical dimensions in millimetres for any plate geometry."""

    width: Decimal | None = Field(default=None, gt=0)
    depth: Decimal | None = Field(default=None, gt=0)
    diameter: Decimal | None = Field(default=None, gt=0)
    thickness: Decimal | None = Field(default=None, gt=0)


class BuildPlateResponse(ApiModel):
    """A physical P-number plate and its printable sides."""

    id: UUID
    plate_code: str
    display_name: str
    description: str | None
    manufacturer: str | None
    product_name: str | None
    shape: str | None
    dimensions_mm: BuildPlateDimensions
    magnetic: bool | None
    flexible: bool | None
    condition: str
    status: str
    preferred_materials: list[str]
    max_bed_temp_c: Decimal | None
    last_cleaned_at: datetime | None
    cleaning_due_after_prints: int
    cleaning_due_after_days: int
    mesh_due_after_prints: int
    mesh_due_after_days: int
    notes: str | None
    record_version: int
    surfaces: list[BuildPlateSurfaceResponse]


class BuildPlateUpdate(ApiModel):
    expected_version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    manufacturer: str | None = Field(default=None, max_length=120)
    product_name: str | None = Field(default=None, max_length=160)
    shape: str | None = Field(default=None, pattern=r"^(rectangular|round|other)$")
    dimensions_mm: BuildPlateDimensions | None = None
    magnetic: bool | None = None
    flexible: bool | None = None
    condition: str | None = None
    status: str | None = None
    preferred_materials: list[str] | None = Field(default=None, max_length=50)
    max_bed_temp_c: Decimal | None = Field(default=None, ge=0, le=500)
    cleaning_due_after_prints: int | None = Field(default=None, ge=1, le=10_000)
    cleaning_due_after_days: int | None = Field(default=None, ge=1, le=3650)
    mesh_due_after_prints: int | None = Field(default=None, ge=1, le=10_000)
    mesh_due_after_days: int | None = Field(default=None, ge=1, le=3650)
    notes: str | None = Field(default=None, max_length=4000)


class BuildPlateSurfaceUpdate(ApiModel):
    """Editable metadata for one immutable plate-side identity."""

    expected_version: int = Field(ge=1)
    surface_material: str | None = Field(default=None, max_length=120)
    texture: PlateSurfaceTexture | None = None
    notes: str | None = Field(default=None, max_length=4000)


class PlateSelectRequest(ApiModel):
    printer_id: UUID
    surface_id: UUID


class BuildPlateSyncRequest(ApiModel):
    """Select the configured canonical printer to synchronize."""

    printer_id: UUID


class BuildPlateSyncResponse(ApiModel):
    """Describe canonical changes made from one Moonraker bed-mesh snapshot."""

    printer_id: UUID
    discovered_codes: list[str]
    created_codes: list[str]
    unavailable_codes: list[str]
    ignored_profile_count: int
    active_mesh_profile: str | None
    active_plate_code: str | None
    active_surface_code: str | None
    active_plate_changed: bool
    active_surface_changed: bool
    synchronized_at: datetime


class BuildPlateMaintenanceCreate(ApiModel):
    maintenance_type: PlateMaintenanceType
    surface_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BuildPlateMaintenanceEventResponse(ApiModel):
    id: UUID
    build_plate_id: UUID
    build_plate_surface_id: UUID | None
    maintenance_type: PlateMaintenanceType
    performed_by: UUID | None
    source: str
    notes: str | None
    occurred_at: datetime


class BuildPlateMaintenanceStatus(ApiModel):
    build_plate_id: UUID
    cleaning_due: bool
    cleaning_prints_since: int
    cleaning_due_at: datetime | None
    surfaces: list[dict[str, Any]]


class CalibrationCreate(ApiModel):
    filament_product_id: UUID
    spool_id: UUID | None = None
    printer_id: UUID
    nozzle_diameter_mm: Decimal = Field(gt=0)
    build_plate_id: UUID | None = None
    build_plate_surface_id: UUID | None = None
    baseline_profile_id: UUID | None = None
    target_layer_height_mm: Decimal | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=4000)


class CalibrationStepUpdate(ApiModel):
    expected_version: int = Field(ge=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    artifact: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=4000)
    complete: bool = False
    repeat: bool = False


class CalibrationStepResponse(ApiModel):
    id: UUID
    step_order: int
    step_key: str
    name: str
    required: bool
    status: CalibrationStepStatus
    inputs: dict[str, Any]
    result: dict[str, Any]
    artifact: dict[str, Any]
    affected_profile_fields: list[str]
    notes: str | None
    record_version: int


class CalibrationResponse(ApiModel):
    id: UUID
    filament_product_id: UUID
    spool_id: UUID | None
    printer_id: UUID
    nozzle_diameter_mm: Decimal
    build_plate_id: UUID | None
    build_plate_surface_id: UUID | None
    status: CalibrationStatus
    notes: str | None
    override_reason: str | None
    record_version: int
    steps: list[CalibrationStepResponse]


class MaterialSettingsInput(ApiModel):
    """Complete typed and extension Cura settings reusable by profiles and templates."""

    chamber_temp_c: Decimal | None = None
    extruder_temp_c: Decimal
    bed_temp_c: Decimal
    flow_percent: Decimal = Field(gt=0)
    print_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    outer_wall_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    inner_wall_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    infill_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    top_bottom_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    initial_layer_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    travel_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    support_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    retraction_distance_mm: Decimal | None = Field(default=None, ge=0)
    retraction_speed_mm_s: Decimal | None = Field(default=None, ge=0)
    cooling_enabled: bool = True
    cooling_min_percent: Decimal = Field(ge=0, le=100)
    cooling_max_percent: Decimal = Field(ge=0, le=100)
    support_overhang_angle_deg: Decimal | None = Field(default=None, ge=0, le=90)
    tree_max_branch_angle_deg: Decimal | None = Field(default=None, ge=0, le=90)
    pressure_advance: Decimal | None = Field(default=None, ge=0, le=2)
    filament_density_g_cm3: Decimal = Field(gt=0)
    preferred_build_plate_surface_id: UUID | None = None
    cura_extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cura_extensions")
    @classmethod
    def validate_cura_extensions(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Keep extension settings scalar, bounded, and unable to shadow typed fields."""

        import math
        import re

        catalog_by_key = {setting.key: setting for setting in CURA_MATERIAL_SETTINGS}
        if len(value) > len(CURA_EXTENSION_SETTING_KEYS):
            raise ValueError("Cura extensions contain too many settings")
        for key, extension_value in value.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key):
                raise ValueError(f"invalid Cura extension key: {key}")
            if extension_value is not None and not isinstance(extension_value, (str, int, float, bool)):
                raise ValueError(f"Cura extension {key} must be a scalar value")
            if isinstance(extension_value, str) and (
                len(extension_value) > 500 or "\n" in extension_value or "\r" in extension_value
            ):
                raise ValueError(f"Cura extension {key} contains invalid text")
            if isinstance(extension_value, float) and not math.isfinite(extension_value):
                raise ValueError(f"Cura extension {key} must be finite")
            if key not in CURA_EXTENSION_SETTING_KEYS:
                raise ValueError(f"unsupported or reserved typed Cura extension key: {key}")
            expected_type = catalog_by_key[key].value_type
            if (
                extension_value is not None
                and expected_type == "boolean"
                and not isinstance(extension_value, bool)
            ):
                raise ValueError(f"Cura extension {key} must be a boolean")
            if extension_value is not None and expected_type == "number":
                if isinstance(extension_value, bool):
                    raise ValueError(f"Cura extension {key} must be numeric")
                if isinstance(extension_value, str) and not re.fullmatch(r"-?\d+(?:\.\d+)?", extension_value):
                    raise ValueError(f"Cura extension {key} must be numeric")
                numeric_value = Decimal(str(extension_value))
                if key == "klipper_smooth_time_factor" and not (
                    Decimal("0.001") <= numeric_value <= Decimal("0.2")
                ):
                    raise ValueError(
                        "Cura extension klipper_smooth_time_factor must be between 0.001 and 0.2"
                    )
        return value

    @field_validator("cooling_max_percent")
    @classmethod
    def validate_fan_range(cls, value: Decimal, info: Any) -> Decimal:
        """Attach an invalid fan range to the maximum-fan input itself."""

        minimum = info.data.get("cooling_min_percent")
        if isinstance(minimum, Decimal) and minimum > value:
            raise ValueError("Maximum fan must be at least the minimum fan")
        return value


class ProfileCreate(MaterialSettingsInput):
    filament_product_id: UUID
    printer_id: UUID
    nozzle_diameter_mm: Decimal = Field(gt=0)
    base_template_revision_id: UUID | None = None


class ProfileRevisionCreate(ApiModel):
    """Compatibility request for directly saving one profile snapshot."""

    expected_profile_version: int = Field(ge=1)
    settings: MaterialSettingsInput


class ProfileDirectUpdate(ApiModel):
    """Directly save current effective settings with optimistic concurrency."""

    expected_profile_version: int = Field(ge=1)
    settings: MaterialSettingsInput


class ProfileResponse(ProfileCreate):
    id: UUID
    version: int
    status: ProfileStatus
    checksum: str | None
    published_at: datetime | None
    record_version: int
    base_template_revision_id: UUID | None = None
    setting_overrides: dict[str, Any] = Field(default_factory=dict)
    override_keys: list[str] = Field(default_factory=list)
    override_count: int = 0
    inheritance_status: str = "inherited"
    base_template_id: UUID | None = None
    base_template_name: str | None = None
    base_template_version: int | None = None
    base_template_settings: MaterialSettingsInput | None = None
    latest_template_revision_id: UUID | None = None
    latest_template_version: int | None = None
    template_update_changes: list[dict[str, Any]] = Field(default_factory=list)
    source_workstation_agent_id: UUID | None
    source_cura_material_id: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cura_settings(self) -> dict[str, object]:
        """Expose the complete material-scoped setting map stored by this version."""

        return cura_settings_for_profile(self)


class CuraMaterialImportRequest(ApiModel):
    """Compatibility import for one workstation-discovered Cura source."""

    agent_id: UUID
    source_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    filament_product_id: UUID
    printer_id: UUID
    nozzle_diameter_mm: Decimal = Field(gt=0)
    preferred_build_plate_surface_id: UUID | None = None
    extruder_temp_c: Decimal | None = Field(default=None, gt=0, le=500)
    bed_temp_c: Decimal | None = Field(default=None, ge=0, le=200)


class CuraMaterialTemplateImportRequest(ApiModel):
    """Compatibility import for one workstation-discovered Cura template."""

    agent_id: UUID
    source_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: str = Field(min_length=1, max_length=160)
    material_type: str = Field(min_length=1, max_length=48)
    description: str | None = Field(default=None, max_length=4000)
    printer_id: UUID
    nozzle_diameter_mm: Decimal = Field(gt=0)
    filament_diameter_mm: Decimal = Field(default=Decimal("1.75"), gt=0)
    filament_density_g_cm3: Decimal = Field(gt=0)
    preferred_build_plate_surface_id: UUID | None = None
    extruder_temp_c: Decimal | None = Field(default=None, gt=0, le=500)
    bed_temp_c: Decimal | None = Field(default=None, ge=0, le=200)


class MaterialTemplateCreate(ApiModel):
    """Create and immediately activate one scoped template."""

    name: str = Field(min_length=1, max_length=160)
    material_type: str = Field(min_length=1, max_length=48)
    description: str | None = Field(default=None, max_length=4000)
    printer_id: UUID
    nozzle_diameter_mm: Decimal = Field(gt=0)
    filament_diameter_mm: Decimal = Field(default=Decimal("1.75"), gt=0)
    settings: MaterialSettingsInput


class MaterialTemplateUpdate(ApiModel):
    """Update mutable template identity metadata with optimistic concurrency."""

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    material_type: str | None = Field(default=None, min_length=1, max_length=48)
    description: str | None = Field(default=None, max_length=4000)
    active: bool | None = None


class MaterialTemplateRevisionCreate(ApiModel):
    """Compatibility request for directly saving template settings."""

    expected_template_version: int = Field(ge=1)
    settings: MaterialSettingsInput


class MaterialTemplateDirectUpdate(ApiModel):
    """Directly save current template settings with optimistic concurrency."""

    expected_template_version: int = Field(ge=1)
    settings: MaterialSettingsInput


class MaterialTemplateRevisionResponse(ApiModel):
    id: UUID
    material_template_id: UUID
    version: int
    status: ProfileStatus
    settings: MaterialSettingsInput
    checksum: str | None
    published_at: datetime | None
    record_version: int
    created_at: datetime


class MaterialTemplateResponse(ApiModel):
    id: UUID
    name: str
    material_type: str
    description: str | None
    printer_id: UUID
    nozzle_diameter_mm: Decimal
    filament_diameter_mm: Decimal
    source_workstation_agent_id: UUID | None
    source_cura_material_id: str | None
    active: bool
    record_version: int
    created_at: datetime
    updated_at: datetime
    revisions: list[MaterialTemplateRevisionResponse]


class IntegrationStatus(ApiModel):
    service: str
    status: str
    detail: str
    checked_at: datetime


class PrinterResponse(ApiModel):
    """Useful canonical printer metadata with connection details excluded."""

    id: UUID
    printer_code: str
    name: str
    nozzle_diameter_mm: Decimal
    build_volume: dict[str, Any]
    manufacturer: str | None
    model: str | None
    kinematics: str | None
    nozzle_material: str | None
    extruder_type: str | None
    klipper_version: str | None
    moonraker_version: str | None
    host_name: str | None
    notes: str | None
    active_plate_id: UUID | None
    active_plate_surface_id: UUID | None
    active_nozzle_id: UUID | None
    status: str
    last_seen_at: datetime | None
    last_info_sync_at: datetime | None
    record_version: int


class NozzleCreate(ApiModel):
    """Create one uniquely labelled physical nozzle."""

    nozzle_code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    diameter_mm: Decimal = Field(gt=0, le=10)
    material: str = Field(min_length=1, max_length=96)
    manufacturer: str | None = Field(default=None, max_length=160)
    product_name: str | None = Field(default=None, max_length=160)
    coating: str | None = Field(default=None, max_length=96)
    purchase_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class NozzleUpdate(ApiModel):
    """Edit physical nozzle metadata with optimistic concurrency."""

    expected_version: int = Field(ge=1)
    diameter_mm: Decimal | None = Field(default=None, gt=0, le=10)
    material: str | None = Field(default=None, min_length=1, max_length=96)
    manufacturer: str | None = Field(default=None, max_length=160)
    product_name: str | None = Field(default=None, max_length=160)
    coating: str | None = Field(default=None, max_length=96)
    purchase_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    retired: bool | None = None


class NozzleInstallRequest(ApiModel):
    printer_id: UUID
    notes: str | None = Field(default=None, max_length=2000)


class NozzleResponse(ApiModel):
    id: UUID
    nozzle_code: str
    diameter_mm: Decimal
    material: str
    manufacturer: str | None
    product_name: str | None
    coating: str | None
    purchase_date: date | None
    status: NozzleStatus
    installed_printer_id: UUID | None = None
    installed_at: datetime | None
    retired_at: datetime | None
    notes: str | None
    record_version: int
    completed_print_count: int = 0
    completed_filament_weight_g: Decimal = Decimal("0")


class NozzleLifecycleEventResponse(ApiModel):
    id: UUID
    nozzle_id: UUID
    printer_id: UUID | None
    event_type: str
    performed_by: UUID | None
    source: str
    notes: str | None
    occurred_at: datetime


class PrinterUpdate(ApiModel):
    """Manual printer fields and overrides protected by optimistic concurrency."""

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    manufacturer: str | None = Field(default=None, max_length=160)
    model: str | None = Field(default=None, max_length=160)
    kinematics: str | None = Field(default=None, max_length=48)
    nozzle_diameter_mm: Decimal | None = Field(default=None, gt=0, le=10)
    nozzle_material: str | None = Field(default=None, max_length=96)
    extruder_type: str | None = Field(default=None, max_length=96)
    build_volume: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("build_volume")
    @classmethod
    def validate_build_volume(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Accept only the small documented printer-envelope representation."""

        if value is None:
            return None
        allowed = {"shape", "x_mm", "y_mm", "z_mm", "diameter_mm"}
        if set(value) - allowed:
            raise ValueError("build volume contains unsupported fields")
        shape = value.get("shape")
        if shape not in {None, "", "rectangular", "round", "other"}:
            raise ValueError("build volume shape is invalid")
        normalized: dict[str, Any] = {}
        if shape not in {None, ""}:
            normalized["shape"] = shape
        for key in allowed - {"shape"}:
            if value.get(key) in {None, ""}:
                continue
            try:
                parsed = Decimal(str(value[key]))
            except (InvalidOperation, TypeError) as exc:
                raise ValueError(f"build volume {key} must be numeric") from exc
            if not parsed.is_finite() or parsed <= 0:
                raise ValueError(f"build volume {key} must be greater than zero")
            normalized[key] = format(parsed, "f")
        return normalized


class DashboardResponse(ApiModel):
    total_spools: int
    needs_weighing: int
    low_spools: int
    empty_spools: int
    active_spool: SpoolResponse | None
    active_plate: BuildPlateResponse | None
    active_plate_surface: BuildPlateSurfaceResponse | None


class Page(ApiModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


class WorkbookImportRunResponse(ApiModel):
    id: UUID
    source_name: str
    source_sha256: str
    dry_run: bool
    status: str
    report: dict[str, Any]
    approved_by: UUID | None
    created_at: datetime
    completed_at: datetime | None
    stored_workbook: bool


class CuraMachineReport(ApiModel):
    """A Cura machine instance discovered inside one user data directory."""

    machine_id: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    definition_id: str | None = Field(default=None, max_length=255)
    quality_definition_id: str | None = Field(default=None, max_length=255)
    quality_type: str | None = Field(default=None, max_length=96)
    variant: str | None = Field(default=None, max_length=255)
    nozzle_diameter_mm: str | None = Field(default=None, max_length=32)


class CuraInstallationReport(ApiModel):
    """Sanitized Cura installation metadata reported by an agent."""

    installation_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=96)
    version: str = Field(min_length=1, max_length=32)
    channel: str = Field(min_length=1, max_length=32)
    path_hint: str = Field(min_length=1, max_length=255)
    setting_version: int | None = Field(default=None, ge=1, le=1000)
    managed_library_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    machines: list[CuraMachineReport] = Field(default_factory=list, max_length=100)


class CuraMaterialReport(ApiModel):
    """Sanitized existing Cura material or print profile offered for import."""

    source_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    installation_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=96)
    name: str = Field(min_length=1, max_length=255)
    brand: str = Field(min_length=1, max_length=160)
    material_type: str = Field(min_length=1, max_length=160)
    color_name: str = Field(min_length=1, max_length=160)
    settings: dict[str, str | bool]
    source_kind: Literal["material", "print_profile"] = "material"
    machine_name: str | None = Field(default=None, max_length=255)
    quality_type: str | None = Field(default=None, max_length=96)
    omitted_setting_count: int = Field(default=0, ge=0, le=len(CURA_MATERIAL_SETTINGS))

    @field_validator("settings")
    @classmethod
    def validate_settings(cls, value: dict[str, str | bool]) -> dict[str, str | bool]:
        """Accept only the configured Cura catalog with bounded scalar values."""

        if len(value) > len(CURA_MATERIAL_SETTINGS):
            raise ValueError("Cura material contains too many settings")
        for key, setting_value in value.items():
            if key not in {setting.key for setting in CURA_MATERIAL_SETTINGS}:
                raise ValueError(f"unsupported Cura material setting: {key}")
            if isinstance(setting_value, str) and (
                len(setting_value) > 500 or "\n" in setting_value or "\r" in setting_value
            ):
                raise ValueError(f"Cura material setting {key} contains invalid text")
        return value


class CuraManagedMaterialReport(CuraMaterialReport):
    """Sanitized edit candidate for one known managed Cura material."""

    material_guid: UUID
    content_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class WorkstationPairingCodeResponse(ApiModel):
    pairing_code: str
    expires_at: datetime


class WorkstationPairRequest(ApiModel):
    pairing_code: str = Field(pattern=r"^fm_pair_[A-Za-z0-9_-]{30,}$", max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    hostname: str = Field(min_length=1, max_length=255)
    platform: str = Field(pattern=r"^(arch_linux|windows_11)$")
    architecture: str = Field(min_length=1, max_length=64)
    agent_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$", max_length=32)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    cura_installations: list[CuraInstallationReport] = Field(default_factory=list, max_length=20)
    cura_materials: list[CuraMaterialReport] = Field(default_factory=list, max_length=200)
    cura_managed_materials: list[CuraManagedMaterialReport] = Field(default_factory=list, max_length=500)


class WorkstationPairResponse(ApiModel):
    agent_id: UUID
    agent_code: str
    agent_token: str


class WorkstationHeartbeat(ApiModel):
    agent_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$", max_length=32)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    cura_installations: list[CuraInstallationReport] = Field(default_factory=list, max_length=20)
    cura_materials: list[CuraMaterialReport] = Field(default_factory=list, max_length=200)
    cura_managed_materials: list[CuraManagedMaterialReport] = Field(default_factory=list, max_length=500)
    last_error: str | None = Field(default=None, max_length=500)


CuraSourceId = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CuraTakeoverMapping(ApiModel):
    """Map one reported Cura source to one existing canonical template."""

    source_id: CuraSourceId
    template_id: UUID


class CuraTakeoverRequest(ApiModel):
    """Atomically apply reviewed mappings and enable authoritative Cura sync."""

    reviewed_source_ids: list[CuraSourceId] = Field(default_factory=list, max_length=200)
    confirmed: bool
    mappings: list[CuraTakeoverMapping] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_unique_mappings(self) -> "CuraTakeoverRequest":
        """Prevent ambiguous last-write-wins mapping behavior."""

        source_ids = [mapping.source_id for mapping in self.mappings]
        template_ids = [mapping.template_id for mapping in self.mappings]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("each Cura source may be mapped only once")
        if len(template_ids) != len(set(template_ids)):
            raise ValueError("each template may receive only one Cura source")
        return self


class ProfileTemplateRebaseRequest(ApiModel):
    """Confirm one filament profile's move to a published template revision."""

    expected_profile_version: int = Field(ge=1)
    target_template_revision_id: UUID


class WorkstationAgentResponse(ApiModel):
    id: UUID
    agent_code: str
    display_name: str
    hostname: str
    platform: str
    architecture: str
    agent_version: str
    enabled: bool
    cura_management_enabled: bool
    capabilities: dict[str, Any]
    cura_installations: list[dict[str, Any]]
    cura_materials: list[dict[str, Any]]
    cura_recovery_status: str
    cura_recovery_message: str | None
    last_recovery_snapshot_at: datetime | None
    last_recovery_restore_at: datetime | None
    last_seen_at: datetime | None
    last_error: str | None
    record_version: int
    created_at: datetime


class WorkstationAgentUpdate(ApiModel):
    expected_version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    cura_management_enabled: bool | None = None


class CuraRecoverySnapshotUpload(ApiModel):
    """Sanitized exact-version Cura settings captured while Cura is closed."""

    snapshot_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, Any]


class CuraRecoverySnapshotUploadResponse(ApiModel):
    """Idempotent acceptance or reset-protection result for an agent capture."""

    accepted: bool
    status: str
    reason: str | None = None
    snapshot_id: UUID | None = None
    snapshot_checksum: str


class CuraRecoverySnapshotResponse(ApiModel):
    """Safe recovery-point metadata shown without raw configuration contents."""

    id: UUID
    agent_id: UUID
    installation_id: str
    cura_version: str
    setting_version: int | None
    snapshot_checksum: str
    file_count: int
    total_bytes: int
    machine_count: int
    quality_profile_count: int
    plugin_count: int
    plugins: list[dict[str, Any]]
    captured_at: datetime
    created_at: datetime


class CuraRecoveryRestoreRequest(ApiModel):
    """Explicit Administrator confirmation for one recovery point."""

    snapshot_id: UUID
    confirmed: bool


class CuraRecoveryRestoreResponse(ApiModel):
    """Sanitized lifecycle state for one queued Cura recovery operation."""

    id: UUID
    agent_id: UUID
    snapshot_id: UUID | None
    requested_by: UUID
    installation_id: str
    cura_version: str
    snapshot_checksum: str
    status: CuraDeploymentStatus
    attempts: int
    next_attempt_at: datetime
    claimed_at: datetime | None
    completed_at: datetime | None
    result: dict[str, Any]
    last_error_class: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class CuraRecoveryRestoreClaimResponse(ApiModel):
    """Leased immutable restore payload returned only to its paired agent."""

    restore_id: UUID
    snapshot_checksum: str
    payload: dict[str, Any]
    lease_expires_at: datetime


class CuraRecoveryRestoreResult(ApiModel):
    """Bounded path-free result from a workstation recovery operation."""

    installation_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=96)
    version: str = Field(pattern=r"^\d+(?:\.\d+){1,3}$", max_length=32)
    status: Literal["restored", "already_current"]
    restored_files: int = Field(ge=0, le=500)
    removed_files: int = Field(ge=0, le=500)
    preferences_merged: bool
    backup_id: str = Field(pattern=r"^[0-9a-f-]{36}/[A-Za-z0-9_.-]+$", max_length=160)
    missing_plugins: list[str] = Field(default_factory=list, max_length=200)


class CuraRecoveryRestoreCompletion(ApiModel):
    """Safe recovery acknowledgement with no local paths or exception text."""

    outcome: Literal["succeeded", "deferred", "failed"]
    result: CuraRecoveryRestoreResult | None = None
    retry_after_seconds: int = Field(default=60, ge=15, le=3600)


class CuraDeploymentCreate(ApiModel):
    agent_ids: list[UUID] | None = Field(default=None, max_length=100)


class CuraDeploymentResponse(ApiModel):
    id: UUID
    agent_id: UUID
    material_profile_id: UUID | None
    requested_by: UUID | None
    status: CuraDeploymentStatus
    profile_checksum: str
    attempts: int
    next_attempt_at: datetime
    claimed_at: datetime | None
    completed_at: datetime | None
    result: dict[str, Any]
    last_error_class: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class CuraDeploymentClaimResponse(ApiModel):
    deployment_id: UUID
    profile_checksum: str
    payload: dict[str, Any]
    lease_expires_at: datetime


class CuraDeploymentCompletion(ApiModel):
    outcome: str = Field(pattern=r"^(succeeded|deferred|failed)$")
    result: dict[str, Any] = Field(default_factory=dict)
    error_class: str | None = Field(default=None, max_length=160)
    error_message: str | None = Field(default=None, max_length=500)
    retry_after_seconds: int = Field(default=60, ge=15, le=3600)


PRINT_DEFECT_TAGS = {
    "stringing",
    "blobs_zits",
    "underextrusion",
    "overextrusion",
    "poor_bridging",
    "poor_overhangs",
    "warping",
    "elephant_foot",
    "weak_layer_adhesion",
    "poor_top_surface",
    "dimensional_error",
    "supports_difficult_to_remove",
    "supports_fused",
    "seam_artifacts",
}


class PrintAssessmentCreate(ApiModel):
    """Create a new append-only assessment revision for a finished print."""

    rating: PrintQualityRating
    defect_tags: list[str] = Field(default_factory=list, max_length=len(PRINT_DEFECT_TAGS))
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("defect_tags")
    @classmethod
    def validate_defect_tags(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(tag not in PRINT_DEFECT_TAGS for tag in value):
            raise ValueError("defect tags must be unique supported values")
        return value


class PrintAssessmentResponse(ApiModel):
    id: UUID
    revision: int
    rating: PrintQualityRating
    defect_tags: list[str]
    notes: str | None
    assessed_by: UUID
    supersedes_id: UUID | None
    created_at: datetime


class PrintMaterialSegmentResponse(ApiModel):
    id: UUID
    segment_number: int
    spool_id: UUID | None
    filament_product_id: UUID | None
    material_profile_id: UUID | None
    material_profile_version: int | None
    source: str
    state_snapshot: dict[str, Any]
    started_at: datetime
    ended_at: datetime | None
    actual_filament_length_mm: Decimal | None
    actual_filament_weight_g: Decimal | None


class PrintJobResponse(ApiModel):
    id: UUID
    printer_id: UUID
    moonraker_job_id: str | None
    moonraker_file_uuid: str | None
    filename: str
    gcode_sha256: str | None
    source: str
    status: PrintJobStatus
    spool_id: UUID | None
    filament_product_id: UUID | None
    material_profile_id: UUID | None
    material_profile_version: int | None
    build_plate_id: UUID | None
    build_plate_surface_id: UUID | None
    nozzle_id: UUID | None
    nozzle_diameter_mm: Decimal | None
    material_guid: str | None
    material_name: str | None
    material_type: str | None
    state_snapshot: dict[str, Any]
    profile_snapshot: dict[str, Any]
    inspection_status: GcodeInspectionStatus
    inspection_policy: str
    inspection: dict[str, Any]
    inspected_at: datetime | None
    slicer: str | None
    slicer_version: str | None
    cura_quality_profile: str | None
    layer_height_mm: Decimal | None
    line_width_mm: Decimal | None
    extruder_temp_c: Decimal | None
    bed_temp_c: Decimal | None
    chamber_temp_c: Decimal | None
    print_speed_mm_s: Decimal | None
    pressure_advance: Decimal | None
    retraction_distance_mm: Decimal | None
    retraction_speed_mm_s: Decimal | None
    flow_percent: Decimal | None
    predicted_filament_length_mm: Decimal | None
    predicted_filament_weight_g: Decimal | None
    actual_filament_length_mm: Decimal | None
    actual_filament_weight_g: Decimal | None
    estimated_duration_seconds: Decimal | None
    print_duration_seconds: Decimal | None
    total_duration_seconds: Decimal | None
    support_configuration: dict[str, Any]
    machine_name: str | None
    timelapse_url: str | None
    started_at: datetime | None
    ended_at: datetime | None
    record_version: int
    segments: list[PrintMaterialSegmentResponse]
    assessments: list[PrintAssessmentResponse]


class OperationalSettingsResponse(ApiModel):
    gcode_inspection_policy: str
    record_version: int


class OperationalSettingsUpdate(ApiModel):
    expected_version: int = Field(ge=1)
    gcode_inspection_policy: str = Field(pattern=r"^(warn|block)$")


class DiagnosticCheck(ApiModel):
    """One sanitized operational or recovery-validation result."""

    key: str
    label: str
    category: str
    status: str
    detail: str
    checked_at: datetime


class DiagnosticErrorEntry(ApiModel):
    """A bounded error summary sourced from canonical operational records."""

    source: str
    severity: str
    summary: str
    detail: str | None
    occurred_at: datetime
    correlation_id: str | None = None


class DiagnosticOverviewResponse(ApiModel):
    checked_at: datetime
    checks: list[DiagnosticCheck]
    queue_counts: dict[str, int]
    job_type_counts: dict[str, int]
    error_log: list[DiagnosticErrorEntry]


class VersionStatusResponse(ApiModel):
    """Running application version and sanitized GitHub release comparison."""

    running_version: str
    latest_version: str | None
    status: str
    release_url: str | None
    detail: str


class DiagnosticRunResponse(ApiModel):
    id: UUID
    run_type: str
    status: str
    requested_by: UUID
    results: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None


class ProjectionRebuildResponse(ApiModel):
    status: str
    queued_jobs: int
    categories: dict[str, int]


class NotificationResponse(ApiModel):
    id: UUID
    category: str
    severity: NotificationSeverity
    title: str
    message: str
    action_path: str | None
    object_type: str | None
    object_id: UUID | None
    active: bool
    occurrence_count: int
    created_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    read: bool
