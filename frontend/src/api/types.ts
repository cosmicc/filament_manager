export type UserRole = 'administrator' | 'operator' | 'viewer'

export interface User {
  id: string
  username: string
  display_name: string
  role: UserRole
  is_active: boolean
  must_change_password: boolean
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
  color_mode: 'solid' | 'multicolor' | 'rainbow'
  color_hexes: string[]
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
  purchase_source: string | null
  purchase_date: string | null
  purchase_cost: string | null
  cost_per_gram: string | null
  currency: string
  location: string | null
  spoolman_id: number | null
  active_printer_id: string | null
  last_measurement_at: string | null
  notes: string | null
  archived: boolean
  record_version: number
  completed_print_count: number
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
  completed_print_count: number
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
  cleaning_due_after_prints: number
  cleaning_due_after_days: number
  mesh_due_after_prints: number
  mesh_due_after_days: number
  notes: string | null
  image_url: string | null
  image_version: number
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
  printer_state: DashboardPrinterState
}

export interface DashboardPrinterState {
  printer_name: string
  connection_status: 'connected' | 'unavailable' | 'not_configured'
  operational_status: 'idle' | 'printing' | 'paused' | 'finished' | 'cancelled' | 'starting' | 'error' | 'unavailable' | 'not_configured'
  klipper_state: 'ready' | 'startup' | 'shutdown' | 'error' | null
  print_state: 'standby' | 'printing' | 'paused' | 'error' | 'complete' | 'cancelled' | null
  filename: string | null
  progress_percent: string | null
  nozzle_temperature_c: string | null
  nozzle_target_c: string | null
  bed_temperature_c: string | null
  bed_target_c: string | null
  chamber_temperature_c: string | null
  chamber_target_c: string | null
  print_job_id: string | null
  thumbnail_url: string | null
  estimated_duration_seconds: string | null
  print_duration_seconds: string | null
  predicted_filament_weight_g: string | null
  actual_filament_weight_g: string | null
  actual_filament_cost: string | null
  predicted_filament_cost: string | null
  cost_currency: string | null
  cost_complete: boolean
  checked_at: string
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
  color_mode: 'solid' | 'multicolor' | 'rainbow'
  color_hexes: string[]
  product_name: string | null
  diameter_mm: string
  tolerance_mm: string | null
  density_g_cm3: string
  nominal_net_mass_g: string
  notes: string | null
  material_template_revision_id: string | null
  archived: boolean
  color_editable: boolean
  record_version: number
}

export interface FilamentColor {
  id: string
  name: string
  normalized_name: string
  color_hex: string
  color_mode: 'solid' | 'multicolor' | 'rainbow'
  color_hexes: string[]
  record_version: number
}

export interface CuraSettingCatalogItem {
  key: string
  label: string
  value_type: 'boolean' | 'number' | 'string'
  unit: string | null
  editable: boolean
  template_only: boolean
}

export interface MaterialSettings {
  chamber_temp_c: string | null
  extruder_temp_c: string
  bed_temp_c: string
  initial_bed_temp_c: string
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
  retraction_prime_speed_mm_s: string | null
  cooling_enabled: boolean
  cooling_min_percent: string
  cooling_max_percent: string
  support_overhang_angle_deg: string | null
  tree_max_branch_angle_deg: string | null
  pressure_advance: string | null
  ironing_flow_percent: string | null
  ironing_speed_mm_s: string | null
  ironing_line_spacing_mm: string | null
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
  nozzle_id: string
  nozzle_diameter_mm: string
  filament_diameter_mm: string
  source_workstation_agent_id: string | null
  source_cura_material_id: string | null
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
  active_nozzle_id: string | null
  status: string
  last_seen_at: string | null
  last_info_sync_at: string | null
  spool_preflight_status: string
  spool_preflight_message: string | null
  last_spool_preflight_sync_at: string | null
  record_version: number
}

export interface Nozzle {
  id: string
  nozzle_code: string
  printer_id: string
  diameter_mm: string
  material: string
  manufacturer: string | null
  product_name: string | null
  coating: string | null
  purchase_date: string | null
  status: 'available' | 'installed' | 'retired'
  installed_printer_id: string | null
  installed_at: string | null
  retired_at: string | null
  notes: string | null
  record_version: number
  completed_print_count: number
  completed_filament_weight_g: string
}

export interface NozzleLifecycleEvent {
  id: string
  nozzle_id: string
  printer_id: string | null
  event_type: 'installed' | 'removed' | 'retired' | 'reactivated'
  performed_by: string | null
  source: string
  notes: string | null
  occurred_at: string
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
  base_template_revision_id: string | null
  setting_overrides: Record<string, unknown>
  override_keys: string[]
  override_count: number
  inheritance_status: 'inherited' | 'customized'
  base_template_id: string | null
  base_template_name: string | null
  base_template_version: number | null
  base_template_settings: MaterialSettings | null
  latest_template_revision_id: string | null
  latest_template_version: number | null
  template_update_changes: Array<{
    key: string
    current_value: unknown
    proposed_value: unknown
    overridden: boolean
  }>
  source_workstation_agent_id: string | null
  source_cura_material_id: string | null
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

export interface CalibrationSuggestions {
  settings: MaterialSettings
  suggestions: Record<string, unknown>
  template_id: string
  template_name: string
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
  last_error_at: string | null
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

export interface CuraMaterialSettingsSyncReport {
  status: 'not_deployed' | 'waiting_for_cura' | 'waiting_for_machine' | 'healthy' | 'degraded' | 'invalid'
  expected_count: number
  exposed_count: number
  missing_keys: string[]
  unexpected_keys: string[]
  material_settings_plugin_ready: boolean
  klipper_settings_plugin_ready: boolean
  plugins: Array<{
    role: 'material_settings' | 'klipper_settings'
    package_id: string
    display_name: string
    version: string
    enabled: boolean
  }>
  catalog_checksum: string | null
  verified_at: string | null
}

export interface CuraInstallationReport {
  installation_id: string
  version: string
  channel: string
  path_hint: string
  setting_version: number | null
  managed_library_checksum: string | null
  material_settings_sync?: CuraMaterialSettingsSyncReport | null
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
  source_kind?: 'material' | 'print_profile'
  machine_name?: string | null
  quality_type?: string | null
  omitted_setting_count?: number
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
  cura_recovery_status: 'not_ready' | 'ready' | 'capture_blocked' | 'restore_pending' | 'restoring' | 'restore_failed' | string
  cura_recovery_message: string | null
  last_recovery_snapshot_at: string | null
  last_recovery_restore_at: string | null
  last_seen_at: string | null
  last_error: string | null
  record_version: number
  created_at: string
}

export interface CuraRecoveryPlugin {
  package_id: string
  display_name: string
  version: string
  enabled: boolean
}

export interface CuraRecoverySnapshot {
  id: string
  agent_id: string
  installation_id: string
  cura_version: string
  setting_version: number | null
  snapshot_checksum: string
  file_count: number
  total_bytes: number
  machine_count: number
  quality_profile_count: number
  plugin_count: number
  plugins: CuraRecoveryPlugin[]
  capture_kind: 'automatic' | 'manual'
  name: string | null
  description: string | null
  record_version: number
  captured_at: string
  created_at: string
}

export interface CuraRecoveryRestore {
  id: string
  agent_id: string
  snapshot_id: string | null
  requested_by: string
  installation_id: string
  cura_version: string
  snapshot_checksum: string
  status: 'pending' | 'claimed' | 'succeeded' | 'failed' | 'cancelled'
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

export interface CuraDeployment {
  id: string
  agent_id: string
  material_profile_id: string | null
  requested_by: string | null
  operation: string
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

export type PrintQualityRating = 'successful' | 'excellent' | 'acceptable' | 'failed'

export interface PrintAssessment {
  id: string
  revision: number
  rating: PrintQualityRating
  defect_tags: string[]
  notes: string | null
  assessed_by: string
  supersedes_id: string | null
  created_at: string
}

export interface PrintMaterialSegment {
  id: string
  segment_number: number
  spool_id: string | null
  filament_product_id: string | null
  material_profile_id: string | null
  material_profile_version: number | null
  source: string
  state_snapshot: Record<string, unknown>
  started_at: string
  ended_at: string | null
  actual_filament_length_mm: string | null
  actual_filament_weight_g: string | null
  cost_per_gram: string | null
  actual_filament_cost: string | null
  cost_currency: string | null
}

export interface PrintJob {
  id: string
  printer_id: string
  moonraker_job_id: string | null
  filename: string
  gcode_sha256: string | null
  source: string
  status: 'in_progress' | 'completed' | 'cancelled' | 'failed' | 'legacy_unknown'
  moonraker_status: 'in_progress' | 'completed' | 'cancelled' | 'error' | 'klippy_shutdown' | 'klippy_disconnect' | 'interrupted' | null
  spool_id: string | null
  filament_product_id: string | null
  material_profile_id: string | null
  material_profile_version: number | null
  build_plate_id: string | null
  build_plate_surface_id: string | null
  nozzle_id: string | null
  nozzle_diameter_mm: string | null
  material_name: string | null
  material_type: string | null
  state_snapshot: Record<string, unknown>
  profile_snapshot: Record<string, unknown>
  print_settings_snapshot: Record<string, unknown>
  inspection_status: 'pending' | 'passed' | 'warning' | 'blocked' | 'unavailable'
  inspection_policy: 'warn' | 'block'
  inspection: {
    extracted?: Record<string, unknown>
    mismatches?: Array<{
      field: string
      label: string
      gcode_value: string
      profile_value: string
    }>
    warnings?: string[]
    printer_gate?: 'active' | 'not_active'
    file_metadata?: Record<string, string | number>
  }
  slicer: string | null
  slicer_version: string | null
  cura_quality_profile: string | null
  layer_height_mm: string | null
  line_width_mm: string | null
  extruder_temp_c: string | null
  bed_temp_c: string | null
  initial_bed_temp_c: string | null
  chamber_temp_c: string | null
  print_speed_mm_s: string | null
  pressure_advance: string | null
  retraction_distance_mm: string | null
  retraction_speed_mm_s: string | null
  flow_percent: string | null
  predicted_filament_length_mm: string | null
  predicted_filament_weight_g: string | null
  actual_filament_length_mm: string | null
  actual_filament_weight_g: string | null
  estimated_duration_seconds: string | null
  print_duration_seconds: string | null
  total_duration_seconds: string | null
  support_configuration: Record<string, unknown>
  machine_name: string | null
  timelapse_url: string | null
  thumbnail_url: string | null
  thumbnail_width: number | null
  thumbnail_height: number | null
  actual_filament_cost: string | null
  predicted_filament_cost: string | null
  cost_currency: string | null
  cost_currency_conflict: boolean
  cost_complete: boolean
  priced_filament_weight_g: string
  unpriced_filament_weight_g: string
  started_at: string | null
  ended_at: string | null
  record_version: number
  segments: PrintMaterialSegment[]
  assessments: PrintAssessment[]
}

export type PrintJobSummary = Omit<PrintJob, 'print_settings_snapshot'>

export interface PrintJobPage {
  items: PrintJobSummary[]
  page: number
  per_page: 10 | 25 | 50 | 100
  total_items: number
  total_pages: number
}

export interface ProfileStatistics {
  rated_prints: number
  ratings: Partial<Record<PrintQualityRating, number>>
  success_rate_percent: string | null
  low_sample: boolean
}

export interface OperationalSettings {
  gcode_inspection_policy: 'warn' | 'block'
  record_version: number
}

export interface DiagnosticCheck {
  key: string
  label: string
  category: 'connection' | 'synchronization' | 'worker' | 'operational' | 'recovery' | string
  status: 'healthy' | 'warning' | 'error' | 'disabled' | string
  detail: string
  checked_at: string
}

export interface DiagnosticErrorEntry {
  source: string
  severity: 'warning' | 'error' | string
  summary: string
  detail: string | null
  occurred_at: string
  correlation_id: string | null
  current: boolean
}

export interface DiagnosticFailureGroup {
  job_type: string
  count: number
  status: string
  attempts: number
  max_attempts: number
  error_class: string
  detail: string | null
  occurred_at: string
}

export interface DiagnosticOverview {
  checked_at: string
  checks: DiagnosticCheck[]
  queue_counts: Record<string, number>
  job_type_counts: Record<string, number>
  failure_groups: DiagnosticFailureGroup[]
  error_log: DiagnosticErrorEntry[]
}

export interface VersionStatus {
  running_version: string
  latest_version: string | null
  status: 'current' | 'update_available' | 'ahead' | 'unavailable' | string
  release_url: string | null
  detail: string
}

export interface DiagnosticRun {
  id: string
  run_type: string
  status: 'running' | 'completed' | 'failed' | string
  requested_by: string
  results: {
    summary?: Record<string, number>
    checks?: DiagnosticCheck[]
    error?: string
  }
  started_at: string
  completed_at: string | null
}

export interface ProjectionRebuildResult {
  status: string
  queued_jobs: number
  categories: Record<string, number>
}

export interface DatabaseBackupPolicy {
  enabled: boolean
  interval_hours: number
  retention_count: number
  record_version: number
}

export interface DatabaseBackupArchive {
  id: string
  created_at: string
  application_version: string
  database_revision: string
  trigger: 'automatic' | 'manual' | 'pre_restore' | string
  storage_kind: 'automatic' | 'manual' | 'imported' | string
  filename: string
  size_bytes: number
  archive_sha256: string
  dump_sha256: string
}

export interface DatabaseBackupOverview {
  policy: DatabaseBackupPolicy
  status: {
    status: string
    checked_at: string | null
    last_success_at: string | null
    consecutive_failures: number
    next_retry_at: string | null
    last_error_message: string | null
  }
  pending_restore: {
    status: string
    request_id?: string
    backup_id?: string
    requested_at?: string
  } | null
  archives: DatabaseBackupArchive[]
}

export interface DatabaseRestorePreparation {
  status: 'pending_maintenance' | string
  request_id: string
  backup_id: string
  requested_at: string
}

export interface OperatorNotification {
  id: string
  category: string
  severity: 'info' | 'warning' | 'error'
  title: string
  message: string
  action_path: string | null
  object_type: string | null
  object_id: string | null
  active: boolean
  occurrence_count: number
  created_at: string
  last_seen_at: string
  resolved_at: string | null
  read: boolean
}

export interface BuildPlateMaintenanceStatus {
  build_plate_id: string
  cleaning_due: boolean
  cleaning_prints_since: number
  cleaning_due_at: string | null
  surfaces: Array<{
    surface_id: string
    surface_code: string
    mesh_due: boolean
    prints_since: number
    due_at: string | null
  }>
}

export interface BuildPlateMaintenanceEvent {
  id: string
  build_plate_id: string
  build_plate_surface_id: string | null
  maintenance_type: 'cleaned' | 'mesh_calibrated'
  performed_by: string | null
  source: string
  notes: string | null
  occurred_at: string
}
