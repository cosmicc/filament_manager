"""Pydantic API contracts kept separate from ORM models."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from filament_manager.models.enums import (
    CalibrationStatus,
    CalibrationStepStatus,
    CuraDeploymentStatus,
    MeasurementSource,
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
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(ApiModel):
    id: UUID
    username: str
    display_name: str
    role: UserRole
    is_active: bool
    record_version: int


class LoginResponse(ApiModel):
    user: UserResponse


class UserCreate(ApiModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=14, max_length=256)
    role: UserRole


class VendorCreate(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    preferred: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class FilamentCreate(ApiModel):
    vendor_id: UUID | None = None
    material_type: str = Field(min_length=1, max_length=48)
    filler: str | None = Field(default=None, max_length=96)
    finish: str | None = Field(default=None, max_length=96)
    color_name: str = Field(min_length=1, max_length=96)
    color_hex: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")
    product_name: str | None = Field(default=None, max_length=160)
    diameter_mm: Decimal = Field(gt=0)
    tolerance_mm: Decimal | None = Field(default=None, ge=0)
    density_g_cm3: Decimal = Field(gt=0)
    nominal_net_mass_g: Decimal = Field(gt=0)
    notes: str | None = Field(default=None, max_length=4000)


class FilamentResponse(FilamentCreate):
    id: UUID
    vendor_name: str | None = None
    record_version: int


class SpoolCreate(ApiModel):
    spool_code: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=64)
    filament_product_id: UUID
    nominal_net_mass_g: Decimal = Field(gt=0)
    tare_mass_g: Decimal = Field(ge=0)
    initial_gross_mass_g: Decimal | None = Field(default=None, ge=0)
    purchase_source: str | None = Field(default=None, max_length=160)
    purchase_date: date | None = None
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    location: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=4000)


class SpoolUpdate(ApiModel):
    expected_version: int = Field(ge=1)
    location: str | None = Field(default=None, max_length=160)
    purchase_source: str | None = Field(default=None, max_length=160)
    purchase_date: date | None = None
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=4000)
    archived: bool | None = None


class SpoolResponse(ApiModel):
    id: UUID
    spool_code: str
    filament_product_id: UUID
    material_type: str
    filler: str | None
    finish: str | None
    color_name: str
    color_hex: str | None
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
    location: str | None
    spoolman_id: int | None
    last_measurement_at: datetime | None
    notes: str | None
    archived: bool
    record_version: int


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


class BuildPlateResponse(ApiModel):
    id: UUID
    plate_code: str
    display_name: str
    klipper_mesh_profile: str
    surface_type: str | None
    condition: str
    status: str
    preferred_materials: list[str]
    last_cleaned_at: datetime | None
    last_mesh_calibrated_at: datetime | None
    notes: str | None
    record_version: int


class BuildPlateUpdate(ApiModel):
    expected_version: int = Field(ge=1)
    surface_type: str | None = Field(default=None, max_length=120)
    condition: str | None = None
    status: str | None = None
    notes: str | None = Field(default=None, max_length=4000)


class PlateSelectRequest(ApiModel):
    printer_id: UUID


class CalibrationCreate(ApiModel):
    filament_product_id: UUID
    spool_id: UUID | None = None
    printer_id: UUID
    nozzle_diameter_mm: Decimal = Field(gt=0)
    build_plate_id: UUID | None = None
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
    status: CalibrationStatus
    notes: str | None
    override_reason: str | None
    record_version: int
    steps: list[CalibrationStepResponse]


class ProfileCreate(ApiModel):
    filament_product_id: UUID
    printer_id: UUID
    nozzle_diameter_mm: Decimal = Field(gt=0)
    chamber_temp_c: Decimal | None = None
    extruder_temp_c: Decimal
    bed_temp_c: Decimal
    flow_percent: Decimal = Field(gt=0)
    print_speed_mm_s: Decimal | None = Field(default=None, gt=0)
    retraction_distance_mm: Decimal | None = Field(default=None, ge=0)
    retraction_speed_mm_s: Decimal | None = Field(default=None, ge=0)
    cooling_enabled: bool = True
    cooling_min_percent: Decimal = Field(ge=0, le=100)
    cooling_max_percent: Decimal = Field(ge=0, le=100)
    support_overhang_angle_deg: Decimal | None = Field(default=None, ge=0, le=90)
    tree_max_branch_angle_deg: Decimal | None = Field(default=None, ge=0, le=90)
    pressure_advance: Decimal | None = Field(default=None, ge=0)
    filament_density_g_cm3: Decimal = Field(gt=0)
    preferred_build_plate_id: UUID | None = None
    cura_extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cura_extensions")
    @classmethod
    def validate_cura_extensions(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Keep extension settings scalar, bounded, and unable to shadow typed fields."""

        import math
        import re

        reserved = {
            "material_print_temperature",
            "material_bed_temperature",
            "material_flow",
            "speed_print",
            "speed_wall_0",
            "speed_wall_x",
            "speed_infill",
            "speed_topbottom",
            "speed_layer_0",
            "speed_travel",
            "speed_support",
            "bridge_wall_speed",
            "retraction_amount",
            "retraction_speed",
            "cool_fan_enabled",
            "cool_fan_speed_min",
            "cool_fan_speed",
            "support_angle",
            "support_tree_angle",
            "ironing_enabled",
            "ironing_flow",
            "speed_ironing",
            "ironing_line_spacing",
        }
        if len(value) > 100:
            raise ValueError("Cura extensions cannot contain more than 100 settings")
        for key, extension_value in value.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", key) or key in reserved:
                raise ValueError(f"invalid or reserved Cura extension key: {key}")
            if extension_value is not None and not isinstance(extension_value, (str, int, float, bool)):
                raise ValueError(f"Cura extension {key} must be a scalar value")
            if isinstance(extension_value, str) and (
                len(extension_value) > 500 or "\n" in extension_value or "\r" in extension_value
            ):
                raise ValueError(f"Cura extension {key} contains invalid text")
            if isinstance(extension_value, float) and not math.isfinite(extension_value):
                raise ValueError(f"Cura extension {key} must be finite")
        return value

    @model_validator(mode="after")
    def validate_fan_range(self) -> "ProfileCreate":
        if self.cooling_min_percent > self.cooling_max_percent:
            raise ValueError("cooling minimum cannot exceed cooling maximum")
        return self


class ProfileResponse(ProfileCreate):
    id: UUID
    version: int
    status: ProfileStatus
    checksum: str | None
    published_at: datetime | None
    record_version: int


class IntegrationStatus(ApiModel):
    service: str
    status: str
    detail: str
    checked_at: datetime


class DashboardResponse(ApiModel):
    total_spools: int
    needs_weighing: int
    low_spools: int
    empty_spools: int
    active_spool: SpoolResponse | None
    active_plate: BuildPlateResponse | None
    integrations: list[IntegrationStatus]


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
    machines: list[CuraMachineReport] = Field(default_factory=list, max_length=100)


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


class WorkstationPairResponse(ApiModel):
    agent_id: UUID
    agent_code: str
    agent_token: str


class WorkstationHeartbeat(ApiModel):
    agent_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$", max_length=32)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    cura_installations: list[CuraInstallationReport] = Field(default_factory=list, max_length=20)
    last_error: str | None = Field(default=None, max_length=500)


class WorkstationAgentResponse(ApiModel):
    id: UUID
    agent_code: str
    display_name: str
    hostname: str
    platform: str
    architecture: str
    agent_version: str
    enabled: bool
    capabilities: dict[str, Any]
    cura_installations: list[dict[str, Any]]
    last_seen_at: datetime | None
    last_error: str | None
    record_version: int
    created_at: datetime


class WorkstationAgentUpdate(ApiModel):
    expected_version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None


class CuraDeploymentCreate(ApiModel):
    agent_ids: list[UUID] | None = Field(default=None, max_length=100)


class CuraDeploymentResponse(ApiModel):
    id: UUID
    agent_id: UUID
    material_profile_id: UUID
    requested_by: UUID
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
