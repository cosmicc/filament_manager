export type UserRole = 'administrator' | 'operator' | 'viewer'

export interface User {
  id: string
  username: string
  display_name: string
  role: UserRole
  is_active: boolean
  record_version: number
}

export interface IntegrationStatus {
  service: string
  status: 'connected' | 'unavailable' | 'disabled' | string
  detail: string
  checked_at: string
}

export interface Spool {
  id: string
  spool_code: string
  filament_product_id: string
  material_type: string
  filler: string | null
  finish: string | null
  color_name: string
  color_hex: string | null
  vendor_name: string | null
  product_name: string | null
  nominal_net_mass_g: string
  tare_mass_g: string
  remaining_mass_expected_g: string
  remaining_mass_measured_g: string | null
  remaining_mass_effective_g: string
  remaining_percent: string
  weight_confidence: string
  status: 'needs_weighing' | 'in_stock' | 'low' | 'empty' | 'archived'
  location: string | null
  spoolman_id: number | null
  last_measurement_at: string | null
  notes: string | null
  archived: boolean
  record_version: number
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface BuildPlateSurface {
  id: string
  build_plate_id: string
  side: 'a' | 'b'
  surface_code: string
  klipper_mesh_profile: string
  surface_material: string | null
  texture: 'smooth' | 'textured' | null
  mesh_available: boolean | null
  last_mesh_checked_at: string | null
  last_mesh_calibrated_at: string | null
  notes: string | null
  record_version: number
}

export interface BuildPlate {
  id: string
  plate_code: string
  display_name: string
  description: string | null
  manufacturer: string | null
  product_name: string | null
  shape: 'rectangular' | 'round' | 'other' | null
  dimensions_mm: {
    width?: string
    depth?: string
    diameter?: string
    thickness?: string
  }
  magnetic: boolean | null
  flexible: boolean | null
  condition: string
  status: string
  preferred_materials: string[]
  max_bed_temp_c: string | null
  last_cleaned_at: string | null
  notes: string | null
  record_version: number
  surfaces: BuildPlateSurface[]
}

export interface BuildPlateSyncResult {
  printer_id: string
  discovered_codes: string[]
  created_codes: string[]
  unavailable_codes: string[]
  ignored_profile_count: number
  active_mesh_profile: string | null
  active_plate_code: string | null
  active_surface_code: string | null
  active_plate_changed: boolean
  active_surface_changed: boolean
  synchronized_at: string
}

export interface DashboardData {
  total_spools: number
  needs_weighing: number
  low_spools: number
  empty_spools: number
  active_spool: Spool | null
  active_plate: BuildPlate | null
  active_plate_surface: BuildPlateSurface | null
  integrations: IntegrationStatus[]
}

export interface Filament {
  id: string
  vendor_id: string | null
  vendor_name: string | null
  material_type: string
  filler: string | null
  finish: string | null
  color_name: string
  color_hex: string | null
  product_name: string | null
  diameter_mm: string
  tolerance_mm: string | null
  density_g_cm3: string
  nominal_net_mass_g: string
  notes: string | null
  material_template_revision_id: string | null
  record_version: number
}

export interface FilamentColor {
  id: string
  name: string
  normalized_name: string
  color_hex: string
  record_version: number
}

export interface CuraSettingCatalogItem {
  key: string
  label: string
  value_type: 'boolean' | 'number' | 'string'
  unit: string | null
  editable: boolean
}

export interface MaterialSettings {
  chamber_temp_c: string | null
  extruder_temp_c: string
  bed_temp_c: string
  flow_percent: string
  print_speed_mm_s: string | null
  outer_wall_speed_mm_s: string | null
  inner_wall_speed_mm_s: string | null
  infill_speed_mm_s: string | null
  top_bottom_speed_mm_s: string | null
  initial_layer_speed_mm_s: string | null
  travel_speed_mm_s: string | null
  support_speed_mm_s: string | null
  retraction_distance_mm: string | null
  retraction_speed_mm_s: string | null
  cooling_enabled: boolean
  cooling_min_percent: string
  cooling_max_percent: string
  support_overhang_angle_deg: string | null
  tree_max_branch_angle_deg: string | null
  pressure_advance: string | null
  filament_density_g_cm3: string
  preferred_build_plate_surface_id: string | null
  cura_extensions: Record<string, string | number | boolean | null>
}

export interface MaterialTemplateRevision {
  id: string
  material_template_id: string
  version: number
  status: string
  settings: MaterialSettings
  checksum: string | null
  published_at: string | null
  record_version: number
  created_at: string
}

export interface MaterialTemplate {
  id: string
  name: string
  material_type: string
  description: string | null
  printer_id: string
  nozzle_diameter_mm: string
  filament_diameter_mm: string
  active: boolean
  record_version: number
  created_at: string
  updated_at: string
  revisions: MaterialTemplateRevision[]
}

export interface Vendor {
  id: string
  name: string
  preferred: boolean
  record_version: number
}

export interface Printer {
  id: string
  printer_code: string
  name: string
  nozzle_diameter_mm: string
  build_volume: {
    shape?: 'rectangular' | 'round' | 'other'
    x_mm?: string
    y_mm?: string
    z_mm?: string
    diameter_mm?: string
  }
  manufacturer: string | null
  model: string | null
  kinematics: string | null
  nozzle_material: string | null
  extruder_type: string | null
  klipper_version: string | null
  moonraker_version: string | null
  host_name: string | null
  notes: string | null
  active_plate_id: string | null
  active_plate_surface_id: string | null
  status: string
  last_seen_at: string | null
  last_info_sync_at: string | null
  record_version: number
}

export interface SeedSystemResult {
  plates: number
  printers: number
}

export interface MaterialProfile extends MaterialSettings {
  id: string
  filament_product_id: string
  printer_id: string
  nozzle_diameter_mm: string
  version: number
  status: string
  cura_settings: Record<string, string | number | boolean>
  published_at: string | null
  checksum: string | null
  record_version: number
  source_template_revision_id: string | null
}

export interface CalibrationStep {
  id: string
  step_order: number
  step_key: string
  name: string
  required: boolean
  status: 'not_started' | 'in_progress' | 'completed' | 'needs_review' | 'skipped'
  inputs: Record<string, unknown>
  result: Record<string, unknown>
  artifact: Record<string, unknown>
  affected_profile_fields: string[]
  notes: string | null
  record_version: number
}

export interface Calibration {
  id: string
  filament_product_id: string
  spool_id: string | null
  printer_id: string
  nozzle_diameter_mm: string
  build_plate_id: string | null
  build_plate_surface_id: string | null
  status: string
  notes: string | null
  override_reason: string | null
  record_version: number
  steps: CalibrationStep[]
}

export interface AuditEvent {
  id: string
  actor_id: string | null
  source: string
  action: string
  object_type: string
  object_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  correlation_id: string
  occurred_at: string
}

export interface OutboxJob {
  id: string
  job_type: string
  aggregate_type: string
  aggregate_id: string
  aggregate_version: number
  status: string
  attempts: number
  next_attempt_at: string
  last_error_class: string | null
  created_at: string
  completed_at: string | null
}

export interface Device {
  id: string
  device_code: string
  device_type: string
  location: string | null
  firmware_version: string | null
  enabled: boolean
  last_seen_at: string | null
}

export interface WorkbookImportRow {
  row_number: number
  spool_code: string
  errors: string[]
  warnings: string[]
}

export interface WorkbookImportReport {
  source: string
  sha256: string
  inventory_columns: number
  populated_rows: number
  valid_rows: number
  invalid_rows: number
  rows: WorkbookImportRow[]
  committed_spools?: number
  committed_profiles?: number
}

export interface WorkbookImportRun {
  id: string
  source_name: string
  source_sha256: string
  dry_run: boolean
  status: 'validated' | 'invalid' | 'committed' | string
  report: WorkbookImportReport
  approved_by: string | null
  created_at: string
  completed_at: string | null
  stored_workbook: boolean
}

export interface WorkbookImportCounts {
  spools: number
  profiles: number
  vendors: number
  products: number
}

export interface CuraMachineReport {
  machine_id: string
  display_name: string
  definition_id: string | null
  quality_definition_id: string | null
  quality_type: string | null
  variant: string | null
  nozzle_diameter_mm: string | null
}

export interface CuraInstallationReport {
  installation_id: string
  version: string
  channel: string
  path_hint: string
  setting_version: number | null
  managed_library_checksum: string | null
  machines: CuraMachineReport[]
}

export interface CuraMaterialReport {
  source_id: string
  installation_id: string
  name: string
  brand: string
  material_type: string
  color_name: string
  settings: Record<string, string | boolean>
}

export interface WorkstationAgent {
  id: string
  agent_code: string
  display_name: string
  hostname: string
  platform: 'arch_linux' | 'windows_11'
  architecture: string
  agent_version: string
  enabled: boolean
  cura_management_enabled: boolean
  capabilities: Record<string, unknown>
  cura_installations: CuraInstallationReport[]
  cura_materials: CuraMaterialReport[]
  last_seen_at: string | null
  last_error: string | null
  record_version: number
  created_at: string
}

export interface CuraDeployment {
  id: string
  agent_id: string
  material_profile_id: string | null
  requested_by: string | null
  status: 'pending' | 'claimed' | 'succeeded' | 'failed' | 'cancelled'
  profile_checksum: string
  attempts: number
  next_attempt_at: string
  claimed_at: string | null
  completed_at: string | null
  result: Record<string, unknown>
  last_error_class: string | null
  last_error_message: string | null
  created_at: string
  updated_at: string
}

export interface WorkstationPairingCode {
  pairing_code: string
  expires_at: string
}
