import { expect, test } from '@playwright/test'

const thumbnailSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300"><defs><linearGradient id="background" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0c2238"/><stop offset="1" stop-color="#17607b"/></linearGradient></defs><rect width="400" height="300" rx="18" fill="url(#background)"/><path d="M200 62 294 114v92l-94 52-94-52v-92z" fill="#d8edf5" stroke="#77c8e4" stroke-width="8"/><path d="m106 114 94 54 94-54M200 168v90" fill="none" stroke="#17607b" stroke-width="8"/><text x="200" y="38" fill="#fff" font-family="sans-serif" font-size="18" text-anchor="middle">G-code preview</text></svg>`

const user = {
  id: '10000000-0000-0000-0000-000000000001',
  username: 'operator',
  display_name: 'Workshop Operator',
  role: 'operator',
  is_active: true,
  must_change_password: false,
  record_version: 1,
}

const printJob = {
  id: '20000000-0000-0000-0000-000000000001',
  printer_id: '30000000-0000-0000-0000-000000000001',
  moonraker_job_id: 'history-42',
  moonraker_file_uuid: 'file-42',
  filename: 'dimensional-cube.gcode',
  gcode_sha256: 'a'.repeat(64),
  source: 'live',
  status: 'completed',
  spool_id: '40000000-0000-0000-0000-000000000001',
  filament_product_id: '50000000-0000-0000-0000-000000000001',
  material_profile_id: '60000000-0000-0000-0000-000000000001',
  material_profile_version: 12,
  build_plate_id: '70000000-0000-0000-0000-000000000001',
  build_plate_surface_id: '80000000-0000-0000-0000-000000000001',
  nozzle_id: '85000000-0000-0000-0000-000000000001',
  nozzle_diameter_mm: '0.4',
  material_guid: '90000000-0000-0000-0000-000000000001',
  material_name: 'Workshop PETG',
  material_type: 'PETG',
  state_snapshot: {
    printer: { name: 'Workshop Printer' }, spool: { code: 'PETG-01' },
    nozzle: { code: 'N4', diameter_mm: '0.4', material: 'Hardened steel' },
    filament: { product_name: 'Workshop PETG' }, build_plate_surface: { code: 'P4b' },
  },
  profile_snapshot: { extruder_temp_c: '235', flow_percent: '96' },
  inspection_status: 'warning',
  inspection_policy: 'warn',
  inspection: {
    extracted: {},
    mismatches: [{ field: 'extruder_temp_c', label: 'printing temperature', gcode_value: '240', profile_value: '235' }],
    warnings: [],
    file_metadata: { size: 1048576, object_height: '25', layer_count: 125 },
  },
  inspected_at: '2026-08-13T20:00:00Z',
  slicer: 'Cura',
  slicer_version: '5.10.1',
  cura_quality_profile: 'Dimensional',
  layer_height_mm: '0.2',
  line_width_mm: '0.44',
  extruder_temp_c: '240',
  initial_bed_temp_c: '85',
  bed_temp_c: '80',
  chamber_temp_c: null,
  print_speed_mm_s: '120',
  pressure_advance: '0.035',
  retraction_distance_mm: '0.8',
  retraction_speed_mm_s: '40',
  flow_percent: '96',
  predicted_filament_length_mm: '10000',
  predicted_filament_weight_g: '30',
  actual_filament_length_mm: '9800',
  actual_filament_weight_g: '29.5',
  estimated_duration_seconds: '3600',
  print_duration_seconds: '3500',
  total_duration_seconds: '3700',
  support_configuration: { enabled: false },
  machine_name: 'workshop_printer',
  timelapse_url: `/api/v1/prints/20000000-0000-0000-0000-000000000001/timelapse`,
  thumbnail_url: `/api/v1/prints/20000000-0000-0000-0000-000000000001/thumbnail`,
  thumbnail_width: 400,
  thumbnail_height: 300,
  actual_filament_cost: '0.89',
  predicted_filament_cost: '0.90',
  cost_currency: 'USD',
  cost_currency_conflict: false,
  cost_complete: true,
  priced_filament_weight_g: '29.5',
  unpriced_filament_weight_g: '0',
  started_at: '2026-08-13T19:00:00Z',
  ended_at: '2026-08-13T20:00:00Z',
  record_version: 2,
  segments: [{
    id: 'a0000000-0000-0000-0000-000000000001', segment_number: 1,
    spool_id: '40000000-0000-0000-0000-000000000001',
    filament_product_id: '50000000-0000-0000-0000-000000000001',
    material_profile_id: '60000000-0000-0000-0000-000000000001',
    material_profile_version: 12, source: 'print_start',
    state_snapshot: { spool: { code: 'PETG-01' } },
    started_at: '2026-08-13T19:00:00Z', ended_at: '2026-08-13T20:00:00Z',
    actual_filament_length_mm: '9800', actual_filament_weight_g: '29.5',
    cost_per_gram: '0.03', actual_filament_cost: '0.89', cost_currency: 'USD',
  }],
  assessments: [],
}

test.beforeEach(async ({ page }) => {
  await page.route('**/runtime-config.js', (route) => route.fulfill({
    contentType: 'application/javascript',
    body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};',
  }))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/notifications**', (route) => route.fulfill({ json: [{
    id: 'b0000000-0000-0000-0000-000000000001', category: 'spool_low', severity: 'warning',
    title: 'Spool PETG-01 is low', message: '92 g remains on this spool.', action_path: '/spools',
    object_type: 'spool', object_id: printJob.spool_id, active: true, occurrence_count: 1,
    created_at: '2026-08-13T20:00:00Z', last_seen_at: '2026-08-13T20:00:00Z',
    resolved_at: null, read: false,
  }] }))
  await page.route('**/api/v1/prints?**', (route) => route.fulfill({ json: [printJob] }))
  await page.route(`**/api/v1/prints/${printJob.id}/thumbnail`, (route) => route.fulfill({
    contentType: 'image/svg+xml',
    body: thumbnailSvg,
  }))
  await page.route(`**/api/v1/prints/${printJob.id}/assessments`, (route) => route.fulfill({ status: 201, json: {
    id: 'c0000000-0000-0000-0000-000000000001', revision: 1, rating: 'successful',
    defect_tags: [], notes: null, assessed_by: user.id, supersedes_id: null,
    created_at: '2026-08-13T20:05:00Z',
  } }))
})

test('exact print state, inspection, scoring, notifications, and mobile cards render', async ({ page }) => {
  await page.goto('/prints')
  await expect(page.getByRole('heading', { name: 'Print history' })).toBeVisible()
  await expect(page.getByText('29.5 g · $0.89', { exact: true })).toBeVisible()
  await page.getByText('dimensional-cube.gcode', { exact: true }).first().click()
  const dialog = page.getByRole('dialog', { name: 'dimensional-cube.gcode' })
  await expect(dialog.getByText('G-code 240; profile 235')).toBeVisible()
  await expect(dialog.getByText('PETG-01', { exact: true })).toBeVisible()
  await expect(dialog.getByText('N4 · 0.4 mm · Hardened steel')).toBeVisible()
  await expect(dialog.getByAltText('Preview of dimensional-cube.gcode')).toBeVisible()
  await expect(dialog.getByText('240 / 85 / 80 / — °C')).toBeVisible()
  await expect(dialog.getByText('$0.89', { exact: true })).toBeVisible()
  await expect(dialog.getByText('3¢/g captured cost', { exact: false })).toBeVisible()
  await expect(dialog.getByText(/SHA-256/)).toHaveCount(0)
  await expect(dialog.getByRole('link', { name: 'Open video' })).toHaveAttribute(
    'href',
    `/api/v1/prints/${printJob.id}/timelapse`,
  )
  await expect(dialog.getByRole('button', { name: 'Save assessment' })).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/print-history-v057.png', fullPage: true })
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: '1 unread notifications' }).click()
  await expect(page.getByText('Spool PETG-01 is low')).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: /dimensional-cube.gcode/ }).click()
  await expect(page.getByRole('dialog', { name: 'dimensional-cube.gcode' })).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/print-history-mobile-v057.png', fullPage: true })
})
