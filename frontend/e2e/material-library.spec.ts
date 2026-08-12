import { expect, test } from '@playwright/test'

const user = {
  id: 'administrator-id', username: 'admin', display_name: 'Administrator',
  role: 'administrator', is_active: true, record_version: 1,
}

const printer = {
  id: 'printer-id', printer_code: 'printer-1', name: 'Workshop Printer',
  nozzle_diameter_mm: '0.4', active_plate_id: null, active_plate_surface_id: null,
  status: 'connected', last_seen_at: '2026-08-11T14:00:00Z', record_version: 1,
}

const settings = {
  chamber_temp_c: null, extruder_temp_c: '210', bed_temp_c: '60', flow_percent: '100',
  print_speed_mm_s: '120', outer_wall_speed_mm_s: '60', inner_wall_speed_mm_s: '90',
  infill_speed_mm_s: '110', top_bottom_speed_mm_s: '70', initial_layer_speed_mm_s: '30',
  travel_speed_mm_s: '200', support_speed_mm_s: '80', retraction_distance_mm: '0.8',
  retraction_speed_mm_s: '40', cooling_enabled: true, cooling_min_percent: '30',
  cooling_max_percent: '100', support_overhang_angle_deg: '55',
  tree_max_branch_angle_deg: '40', pressure_advance: '0.035',
  filament_density_g_cm3: '1.24', preferred_build_plate_surface_id: null,
  cura_extensions: { retraction_enable: true, klipper_smooth_time_enable: true },
}

const template = {
  id: 'template-id', name: 'Generic PLA', material_type: 'PLA',
  description: 'Starting settings for ordinary PLA', printer_id: printer.id,
  nozzle_diameter_mm: '0.4', filament_diameter_mm: '1.75', active: true,
  record_version: 2, created_at: '2026-08-11T12:00:00Z', updated_at: '2026-08-11T13:00:00Z',
  revisions: [{
    id: 'revision-id', material_template_id: 'template-id', version: 1,
    status: 'published', settings, checksum: 'a'.repeat(64),
    published_at: '2026-08-11T13:00:00Z', record_version: 2,
    created_at: '2026-08-11T12:00:00Z',
  }],
}

const filament = {
  id: 'filament-id', vendor_id: null, vendor_name: null, material_type: 'PLA',
  filler: null, finish: null, color_name: 'Blue', color_hex: '2F80A5',
  product_name: 'Workshop PLA', diameter_mm: '1.75', tolerance_mm: null,
  density_g_cm3: '1.24', nominal_net_mass_g: '1000', notes: null,
  material_template_revision_id: 'revision-id', record_version: 1,
}

const spool = {
  id: 'spool-id', spool_code: 'PLA-BLUE-01', filament_product_id: filament.id,
  material_type: 'PLA', filler: null, finish: null, color_name: 'Blue',
  color_hex: '2F80A5', vendor_name: null, product_name: 'Workshop PLA',
  nominal_net_mass_g: '1000', tare_mass_g: '200', remaining_mass_expected_g: '800',
  remaining_mass_measured_g: '800', remaining_mass_effective_g: '800',
  remaining_percent: '80', weight_confidence: 'measured', status: 'in_stock',
  location: 'Bucket 3', spoolman_id: 7, last_measurement_at: '2026-08-11T14:00:00Z',
  notes: null, archived: false, record_version: 3,
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/printers', (route) => route.fulfill({ json: [printer] }))
  await page.route('**/api/v1/build-plates', (route) => route.fulfill({ json: [] }))
})

test('template library is usable at desktop and mobile sizes', async ({ page }) => {
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [
    { key: 'retraction_enable', label: 'Enable Retraction', value_type: 'boolean', unit: null, editable: true },
    { key: 'klipper_smooth_time_enable', label: 'Enable Klipper Smooth Time', value_type: 'boolean', unit: null, editable: true },
  ] }))
  await page.goto('/templates')
  await expect(page.getByRole('heading', { name: 'Generic PLA' })).toBeVisible()
  await expect(page.getByText('Workshop Printer')).toBeVisible()
  await page.getByRole('button', { name: 'New revision' }).click()
  await expect(page.getByRole('heading', { name: 'Copy and adjust settings' })).toBeVisible()
  await expect(page.getByLabel('Printing temperature (°C)')).toHaveValue('210')
  await page.getByText(/All additional Cura Material Settings/).click()
  await expect(page.getByText('Enable Klipper Smooth Time', { exact: true })).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('heading', { name: 'Copy and adjust settings' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save new revision' })).toBeVisible()
})

test('filament creation requires and submits a published template', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  await page.route('**/api/v1/profiles/templates', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/vendors', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filaments', async (route) => {
    if (route.request().method() === 'POST') {
      submitted = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({ status: 201, json: filament })
    } else await route.fulfill({ json: [] })
  })
  await page.goto('/filaments')
  await page.getByRole('button', { name: 'Add filament' }).click()
  await page.getByLabel('Product name').fill('Workshop PLA')
  await page.getByLabel('Color name').fill('Blue')
  await page.getByRole('button', { name: 'Create filament' }).click()
  await expect.poll(() => submitted?.material_template_revision_id).toBe('revision-id')
  await expect.poll(() => submitted?.material_type).toBe('PLA')
  await expect(page.getByText(/new draft profile copied/)).toBeVisible()
})

test('spool creation is available without opening Spoolman', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [filament] }))
  await page.route('**/api/v1/spools?**', async (route) => {
    if (route.request().method() === 'POST') {
      submitted = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({ status: 201, json: {} })
    } else await route.fulfill({ json: { items: [], total: 0, limit: 200, offset: 0 } })
  })
  await page.route('**/api/v1/spools', async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ status: 201, json: {} })
  })
  await page.goto('/spools')
  await page.getByRole('button', { name: 'Add spool' }).click()
  await page.getByLabel('Spool code').fill('PLA-BLUE-01')
  await page.getByRole('button', { name: 'Create spool' }).click()
  await expect.poll(() => submitted?.filament_product_id).toBe('filament-id')
  await expect.poll(() => submitted?.spool_code).toBe('PLA-BLUE-01')
})

test('free-text bucket location is editable from Filament Manager', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [filament] }))
  await page.route('**/api/v1/spools?**', (route) => route.fulfill({
    json: { items: [spool], total: 1, limit: 200, offset: 0 },
  }))
  await page.route('**/api/v1/spools/spool-id', async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ json: { ...spool, location: 'Bucket 12', record_version: 4 } })
  })

  await page.goto('/spools')
  await page.getByText('PLA-BLUE-01', { exact: true }).click()
  await expect(page.getByText('Bucket 3', { exact: true }).last()).toBeVisible()
  await page.getByRole('button', { name: 'Edit location' }).click()
  await page.getByLabel('Bucket or location').fill('Bucket 12')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Save location' }).click()

  await expect.poll(() => submitted?.expected_version).toBe(3)
  await expect.poll(() => submitted?.location).toBe('Bucket 12')
  await expect(page.getByText('Bucket 12', { exact: true })).toBeVisible()
})

test('existing Cura materials require an explicit takeover warning', async ({ page }) => {
  const agent = {
    id: 'agent-id', agent_code: 'WS-TEST', display_name: 'Arch Cura', hostname: 'workstation',
    platform: 'arch_linux', architecture: 'x86_64', agent_version: '0.1.2', enabled: true,
    cura_management_enabled: false, capabilities: { unmanaged_material_count: 18 },
    cura_installations: [{ installation_id: 'cura-id', version: '5.13', channel: 'Linux Cura', path_hint: 'Linux Cura user data / 5.13', setting_version: 27, managed_library_checksum: null, machines: [] }],
    cura_materials: [], last_seen_at: '2026-08-11T14:00:00Z', last_error: null,
    record_version: 1, created_at: '2026-08-11T12:00:00Z',
  }
  let accepted = false
  await page.route('**/api/v1/workstation-agents', (route) => route.fulfill({ json: [agent] }))
  await page.route('**/api/v1/cura-deployments', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/workstation-agents/agent-id', async (route) => {
    accepted = true
    await route.fulfill({ json: { ...agent, cura_management_enabled: true, record_version: 2 } })
  })
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('back up and replace every user material file')
    await dialog.accept()
  })
  await page.goto('/workstations')
  await expect(page.getByText('18', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Manage and synchronize Cura' }).click()
  await expect.poll(() => accepted).toBe(true)
})
