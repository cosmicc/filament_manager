import { expect, test, type Page } from '@playwright/test'

const browserErrors = new WeakMap<Page, string[]>()

async function captureEvidence(page: Page, name: string): Promise<void> {
  const directory = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
  if (directory) await page.screenshot({ path: `${directory}/${name}.png`, fullPage: false })
}

const user = {
  id: 'administrator-id', username: 'admin', display_name: 'Administrator',
  role: 'administrator', is_active: true, must_change_password: false, record_version: 1,
}

const printer = {
  id: 'printer-id', printer_code: 'printer-1', name: 'Workshop Printer',
  nozzle_diameter_mm: '0.4', active_plate_id: null, active_plate_surface_id: null,
  status: 'connected', last_seen_at: '2026-08-11T14:00:00Z', record_version: 1,
}

const nozzle = {
  id: 'nozzle-id', nozzle_code: 'NZ-040', printer_id: printer.id, diameter_mm: '0.4',
  material: 'Hardened steel', manufacturer: 'Workshop', product_name: 'Standard flow',
  coating: null, purchase_date: null, status: 'installed', installed_printer_id: printer.id,
  installed_at: '2026-08-11T14:00:00Z', retired_at: null, notes: null,
  record_version: 1, completed_print_count: 0, completed_filament_weight_g: '0',
}

const settings = {
  chamber_temp_c: null, extruder_temp_c: '210', bed_temp_c: '60', flow_percent: '100',
  print_speed_mm_s: '120', outer_wall_speed_mm_s: '60', inner_wall_speed_mm_s: '90',
  infill_speed_mm_s: '110', top_bottom_speed_mm_s: '70', initial_layer_speed_mm_s: '30',
  travel_speed_mm_s: '200', support_speed_mm_s: '80', retraction_distance_mm: '0.8',
  retraction_speed_mm_s: '40', retraction_prime_speed_mm_s: '36', cooling_enabled: true, cooling_min_percent: '30',
  cooling_max_percent: '100', support_overhang_angle_deg: '55',
  tree_max_branch_angle_deg: '40', pressure_advance: '0.035',
  ironing_flow_percent: null, ironing_speed_mm_s: null, ironing_line_spacing_mm: null,
  filament_density_g_cm3: '1.24', preferred_build_plate_surface_id: null,
  cura_extensions: { retraction_enable: true, klipper_smooth_time_enable: true },
}

const template = {
  id: 'template-id', name: 'Template PLA', material_type: 'PLA',
  description: 'Starting settings for ordinary PLA', printer_id: printer.id, nozzle_id: nozzle.id,
  nozzle_diameter_mm: '0.4', filament_diameter_mm: '1.75', active: true,
  source_workstation_agent_id: null, source_cura_material_id: null,
  record_version: 2, created_at: '2026-08-11T12:00:00Z', updated_at: '2026-08-11T13:00:00Z',
  revisions: [{
    id: 'revision-id', material_template_id: 'template-id', version: 1,
    status: 'published', settings, checksum: 'a'.repeat(64),
    published_at: '2026-08-11T13:00:00Z', record_version: 2,
    created_at: '2026-08-11T12:00:00Z',
  }],
}

const filament = {
  id: 'd1e1d7ce-f0bc-46f5-86b2-d2c74f272f00', vendor_id: null, vendor_name: null, material_type: 'PLA',
  filler: 'Carbon Fiber', finish: 'Silk', color_name: 'Blue', color_hex: '2F80A5',
  color_mode: 'solid', color_hexes: ['2F80A5'],
  product_name: 'Workshop PLA', diameter_mm: '1.75', tolerance_mm: null,
  density_g_cm3: '1.24', nominal_net_mass_g: '1000', notes: null,
  material_template_revision_id: 'revision-id', archived: false, color_editable: true, record_version: 1,
}

const comparisonProfile = {
  ...settings,
  id: 'comparison-profile-id', filament_product_id: filament.id, printer_id: printer.id,
  nozzle_diameter_mm: '0.4', version: 1, status: 'published',
  extruder_temp_c: '215', flow_percent: '100.000',
  cura_extensions: { ...settings.cura_extensions, retraction_enable: false },
  cura_settings: { material_print_temperature: '215', retraction_enable: false },
  published_at: '2026-08-11T13:00:00Z', checksum: 'b'.repeat(64), record_version: 1,
  base_template_revision_id: 'revision-id', setting_overrides: {}, override_keys: [],
  override_count: 0, inheritance_status: 'inherited', base_template_id: template.id,
  base_template_name: template.name, base_template_version: 1, base_template_settings: settings,
  latest_template_revision_id: 'revision-id', latest_template_version: 1,
  template_update_changes: [],
}

const differentScopeProfile = {
  ...comparisonProfile,
  id: 'different-scope-profile-id', nozzle_diameter_mm: '0.6', version: 2,
  extruder_temp_c: '220', record_version: 2,
}

const spool = {
  id: 'spool-id', spool_code: 'PLA-BLUE-01', filament_product_id: filament.id,
  material_type: 'PLA', filler: 'Carbon Fiber', finish: 'Silk', color_name: 'Blue',
  color_hex: '2F80A5', color_mode: 'solid', color_hexes: ['2F80A5'], vendor_name: null, product_name: 'Workshop PLA',
  nominal_net_mass_g: '1000', tare_mass_g: '200', remaining_mass_expected_g: '800',
  remaining_mass_measured_g: '800', remaining_mass_effective_g: '800',
  remaining_percent: '80', weight_confidence: 'measured', status: 'in_stock',
  purchase_source: null, purchase_date: null, purchase_cost: '15.00', cost_per_gram: '0.015000', currency: 'USD',
  location: 'Bucket 3', spoolman_id: 7, active_printer_id: null, last_measurement_at: '2026-08-11T14:00:00Z',
  notes: null, archived: false, record_version: 3, completed_print_count: 6,
}

test.beforeEach(async ({ page }) => {
  const errors: string[] = []
  browserErrors.set(page, errors)
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/runtime-config.js', (route) => route.fulfill({
    contentType: 'application/javascript',
    body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};',
  }))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/printers', (route) => route.fulfill({ json: [printer] }))
  await page.route('**/api/v1/nozzles', (route) => route.fulfill({ json: [nozzle] }))
  await page.route('**/api/v1/build-plates', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/notifications**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filament-colors', (route) => route.fulfill({ json: [
    { id: 'blue-id', name: 'Blue', normalized_name: 'blue', color_hex: '2F80A5', color_mode: 'solid', color_hexes: ['2F80A5'], record_version: 1 },
  ] }))
})

test.afterEach(async ({ page }) => {
  expect(browserErrors.get(page) ?? [], 'browser console and page errors').toEqual([])
})

test('template library is usable at desktop and mobile sizes', async ({ page }) => {
  let templateUpdate: Record<string, unknown> | null = null
  let templateFetchCount = 0
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => {
    templateFetchCount += 1
    return route.fulfill({ json: [{ ...template, record_version: templateFetchCount === 1 ? 2 : 3 }] })
  })
  await page.route('**/api/v1/profiles/templates/template-id/settings', async (route) => {
    templateUpdate = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ json: template })
  })
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [
    { key: 'retraction_enable', label: 'Enable Retraction', value_type: 'boolean', unit: null, editable: true, template_only: false },
    { key: 'klipper_smooth_time_enable', label: 'Enable Klipper Smooth Time', value_type: 'boolean', unit: null, editable: true, template_only: true },
  ] }))
  await page.goto('/templates')
  await expect(page.getByRole('heading', { name: 'Template PLA' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Import from Cura' })).toHaveAttribute('href', '/workstations')
  await expect(page.getByText('Workshop Printer')).toBeVisible()
  await expect(page.getByText('NZ-040 · 0.4 mm Hardened steel')).toBeVisible()
  await expect(page.getByText('Starting settings for ordinary PLA')).toHaveCount(0)
  const templateCard = page.locator('.catalog-card--template')
  await expect.poll(() => templateCard.evaluate((card) => card.scrollWidth <= card.clientWidth)).toBe(true)
  await page.getByRole('button', { name: 'Edit template' }).click()
  await expect(page.getByRole('dialog', { name: 'Edit Template PLA' })).toBeVisible()
  await expect(page.getByLabel('Printing temperature (°C)')).toHaveValue('210')
  await expect(page.getByRole('heading', { name: 'Retraction' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Klipper' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /Advanced Cura-only Settings/ })).toHaveCount(0)
  await expect(page.getByText('Enable Klipper Smooth Time', { exact: true })).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('dialog', { name: 'Edit Template PLA' })).toBeVisible()
  await page.getByLabel('Printing temperature (°C)').fill('212')
  await page.getByLabel('Ironing flow (%)').fill('12')
  await page.getByLabel('Ironing speed (mm/s)').fill('25')
  await page.getByLabel('Ironing line spacing (mm)').fill('0.12')
  await page.getByRole('button', { name: 'Save template' }).click()
  await expect.poll(() => templateUpdate?.expected_template_version).toBe(3)
  await expect.poll(() => (templateUpdate?.settings as Record<string, unknown>)?.extruder_temp_c).toBe('212')
  await expect.poll(() => (templateUpdate?.settings as Record<string, unknown>)?.ironing_flow_percent).toBe('12')
  await expect.poll(() => (templateUpdate?.settings as Record<string, unknown>)?.ironing_speed_mm_s).toBe('25')
  await expect.poll(() => (templateUpdate?.settings as Record<string, unknown>)?.ironing_line_spacing_mm).toBe('0.12')
})

test('blank template values expose and persist copy choices from other templates', async ({ page }) => {
  let templateUpdate: Record<string, unknown> | null = null
  const sourceTemplate = {
    ...template,
    id: 'source-template-id',
    name: 'Template PETG',
    material_type: 'PETG',
    revisions: [{
      ...template.revisions[0],
      id: 'source-revision-id',
      material_template_id: 'source-template-id',
      settings: { ...settings, chamber_temp_c: '45' },
    }],
  }
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [template, sourceTemplate] }))
  await page.route('**/api/v1/profiles/templates/template-id/settings', async (route) => {
    templateUpdate = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ json: template })
  })
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [] }))

  await page.goto('/templates')
  const targetCard = page.locator('.catalog-card--template').filter({ hasText: 'Template PLA' })
  await targetCard.getByRole('button', { name: 'Edit template' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit Template PLA' })
  const copyTemperature = dialog.getByLabel('Copy Build volume temperature from another template')
  await expect(copyTemperature).toBeVisible()
  await expect(copyTemperature).toBeEnabled()
  await expect(copyTemperature.locator('option')).toHaveText(['Choose a populated template…', 'Template PETG · Workshop Printer · 0.4 mm · 45'])
  await page.setViewportSize({ width: 390, height: 844 })
  await copyTemperature.scrollIntoViewIfNeeded()
  await copyTemperature.selectOption('source-template-id')
  await expect(dialog.getByLabel('Build volume temperature (°C)')).toHaveValue('45')
  await expect(copyTemperature).toHaveCount(0)

  const noIroningSource = dialog.getByLabel('Copy Ironing flow from another template')
  await expect(noIroningSource).toBeVisible()
  await expect(noIroningSource).toBeDisabled()
  await expect(noIroningSource).toContainText('No other active template has a value')
  await dialog.getByRole('button', { name: 'Save template' }).click()
  await expect.poll(() => (templateUpdate?.settings as Record<string, unknown>)?.chamber_temp_c).toBe('45')
})

test('template validation centers, focuses, and highlights the rejected setting', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/profiles/templates/template-id/settings', (route) => route.fulfill({
    status: 422,
    json: {
      code: 'validation_error',
      message: 'Request validation failed',
      errors: [{
        field: 'settings.cooling_max_percent',
        message: 'Maximum fan must be at least the minimum fan',
        type: 'value_error',
      }],
    },
  }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [] }))

  await page.goto('/templates')
  await page.getByRole('button', { name: 'Edit template' }).click()
  await page.getByLabel('Regular fan speed (%)').fill('90')
  const maximumFan = page.getByLabel('Maximum fan speed (%)')
  await maximumFan.fill('20')
  await page.getByRole('button', { name: 'Save template' }).click()

  await expect(maximumFan).toHaveAttribute('aria-invalid', 'true')
  await expect(maximumFan).toBeFocused()
  await expect(page.getByText('Maximum fan must be at least the minimum fan', { exact: true })).toBeVisible()
  await expect(page.getByText('Correct the following values and save again:')).toBeVisible()
  await expect(page.locator('.form-error--summary')).toContainText('Maximum fan speed: Maximum fan must be at least the minimum fan')
  const invalidSetting = maximumFan.locator('xpath=ancestor::div[contains(@class, "setting-field")][1]')
  await expect(invalidSetting).toHaveClass(/setting-field--invalid/)
  await expect.poll(async () => {
    const box = await maximumFan.boundingBox()
    return box ? Math.abs((box.y + box.height / 2) - 422) : Number.POSITIVE_INFINITY
  }).toBeLessThan(190)
  const errors = browserErrors.get(page) ?? []
  expect(errors.some((error) => error.includes('[Filament Manager API] Request rejected'))).toBe(true)
  expect(errors.filter((error) => (
    !error.includes('[Filament Manager API] Request rejected')
    && !error.includes('Failed to load resource: the server responded with a status of 422')
  ))).toEqual([])
  browserErrors.set(page, [])
})

test('comparison shows only differences and warns across profile scopes', async ({ page }) => {
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [comparisonProfile, differentScopeProfile] }))
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [filament] }))
  await page.route('**/api/v1/workstation-agents', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [
    { key: 'retraction_enable', label: 'Enable Retraction', value_type: 'boolean', unit: null, editable: true, template_only: false },
    { key: 'klipper_smooth_time_enable', label: 'Enable Klipper Smooth Time', value_type: 'boolean', unit: null, editable: true, template_only: true },
  ] }))
  await page.route('**/api/v1/prints/profile-statistics**', (route) => route.fulfill({ json: {
    [comparisonProfile.id]: { rated_prints: 12, ratings: { successful: 10, failed: 2 }, success_rate_percent: '83.3', low_sample: false },
    [differentScopeProfile.id]: { rated_prints: 3, ratings: { successful: 3 }, success_rate_percent: '100.0', low_sample: true },
  } }))

  await page.goto('/templates')
  await page.getByRole('button', { name: 'Compare settings' }).click()
  const dialog = page.getByRole('dialog', { name: 'Compare material settings' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('2 setting differences')).toBeVisible()
  await expect(dialog.getByText('Printing temperature', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Enable Retraction', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Flow', { exact: true })).toHaveCount(0)
  await expect(dialog.getByText('All selected printer and nozzle scopes match.')).toBeVisible()
  await expect(dialog.getByText('83.3%')).toBeVisible()

  await dialog.getByRole('checkbox', { name: /0\.6 mm nozzle/ }).check()
  await expect(dialog.getByRole('alert')).toContainText('nozzle diameter differ')
  await page.setViewportSize({ width: 390, height: 844 })
  await dialog.getByText('220 °C', { exact: true }).scrollIntoViewIfNeeded()
  await expect(dialog.getByText('220 °C', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Close comparison' })).toBeVisible()
  await dialog.getByRole('button', { name: 'Close comparison' }).click()

  await page.goto('/profiles')
  await expect(page).toHaveURL(/\/filaments\/settings$/)
  await expect(page.getByRole('heading', { name: 'Print settings' })).toBeVisible()
  await page.getByRole('button', { name: 'Compare settings', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Compare material settings' })).toBeVisible()
})

test('filament creation requires and submits a current template', async ({ page }) => {
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
  await page.getByLabel('Display name').fill('Workshop PLA')
  await page.getByRole('combobox', { name: /^Color name/ }).fill('Workshop Sunset')
  await page.getByLabel('Display type').selectOption('multicolor')
  await page.getByLabel('Number of colors').selectOption('3')
  await page.getByLabel('Color 1').fill('#ff0000')
  await page.getByLabel('Color 2').fill('#00ff00')
  await page.getByLabel('Color 3').fill('#0000ff')
  await page.getByRole('button', { name: 'Create filament' }).click()
  await expect.poll(() => submitted?.material_template_revision_id).toBe('revision-id')
  await expect.poll(() => submitted?.material_type).toBe('PLA')
  await expect.poll(() => submitted?.color_mode).toBe('multicolor')
  await expect.poll(() => submitted?.color_hexes).toEqual(['FF0000', '00FF00', '0000FF'])
  await expect(page.getByText(/first printer\/nozzle print-settings scope/)).toBeVisible()
})

test('filament details remember colors and save Cura settings directly', async ({ page }) => {
  let currentFilament = filament
  let filamentUpdate: Record<string, unknown> | null = null
  let profileUpdate: Record<string, unknown> | null = null
  const profile = {
    ...settings,
    id: 'profile-id', filament_product_id: filament.id, printer_id: printer.id,
    nozzle_diameter_mm: '0.4', version: 1, status: 'published',
    cura_extensions: { ...settings.cura_extensions, xy_offset: '0.05' },
    cura_settings: { material_print_temperature: '210', xy_offset: '0.05' },
    published_at: '2026-08-11T13:00:00Z', checksum: 'c'.repeat(64), record_version: 1,
    base_template_revision_id: 'revision-id',
    setting_overrides: { extruder_temp_c: '210', cura_extensions: { xy_offset: '0.05' } },
    override_keys: ['extruder_temp_c', 'xy_offset'], override_count: 2,
    inheritance_status: 'customized', base_template_id: template.id,
    base_template_name: template.name, base_template_version: 1,
    base_template_settings: settings, latest_template_revision_id: 'revision-id',
    latest_template_version: 1, template_update_changes: [],
  }
  const secondaryProfile = {
    ...profile,
    id: 'profile-06',
    nozzle_diameter_mm: '0.6',
    version: 2,
    record_version: 2,
    base_template_name: 'Template PLA 0.6',
    extruder_temp_c: '220',
    cura_settings: { material_print_temperature: '220', xy_offset: '0.05' },
  }
  await page.route(`**/api/v1/filaments/${filament.id}`, async (route) => {
    if (route.request().method() === 'PATCH') {
      filamentUpdate = route.request().postDataJSON() as Record<string, unknown>
      currentFilament = {
        ...currentFilament,
        color_name: String(filamentUpdate.color_name),
        color_hex: String(filamentUpdate.color_hex),
        color_mode: String(filamentUpdate.color_mode),
        color_hexes: filamentUpdate.color_hexes as string[],
        record_version: 2,
      }
    }
    await route.fulfill({ json: currentFilament })
  })
  await page.route('**/api/v1/vendors', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles/templates?include_inactive=false', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [profile, secondaryProfile] }))
  await page.route('**/api/v1/profiles/cura-settings/catalog', (route) => route.fulfill({ json: [
    { key: 'xy_offset', label: 'Horizontal Expansion', value_type: 'number', unit: 'mm', editable: true, template_only: false },
    { key: 'hole_xy_offset', label: 'Hole Horizontal Expansion', value_type: 'number', unit: 'mm', editable: true, template_only: false },
    { key: 'retraction_retract_speed', label: 'Retraction Retract Speed', value_type: 'number', unit: 'mm/s', editable: true, template_only: false },
    { key: 'retraction_prime_speed', label: 'Retraction Prime Speed', value_type: 'number', unit: 'mm/s', editable: true, template_only: false },
    { key: 'cool_fan_speed_max', label: 'Maximum Fan Speed', value_type: 'number', unit: '%', editable: true, template_only: false },
    { key: 'cool_fan_full_layer', label: 'Regular Fan Speed at Layer', value_type: 'number', unit: null, editable: true, template_only: false },
    { key: 'cool_min_layer_time', label: 'Minimum Layer Time', value_type: 'number', unit: 's', editable: true, template_only: false },
    { key: 'cool_min_layer_time_fan_speed_max', label: 'Minimum Layer Time at Maximum Fan', value_type: 'number', unit: 's', editable: true, template_only: false },
    { key: 'cool_min_speed', label: 'Minimum Speed', value_type: 'number', unit: 'mm/s', editable: true, template_only: false },
    { key: 'cool_fan_speed_0', label: 'Initial Fan Speed', value_type: 'number', unit: '%', editable: true, template_only: false },
  ] }))
  await page.route('**/api/v1/profiles/profile-id/settings', async (route) => {
    profileUpdate = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ status: 201, json: { ...profile, id: 'profile-v2', version: 2 } })
  })

  await page.goto(`/filaments/${filament.id}`)
  await expect(page.getByRole('heading', { name: 'Workshop PLA' })).toBeVisible()
  await expect(page.getByText('Template PLA', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '0.4 mm nozzle' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '0.6 mm nozzle' })).toBeVisible()
  await page.getByRole('button', { name: 'Edit product' }).click()
  await expect(page.getByRole('dialog', { name: 'Edit filament product' })).toBeVisible()
  await page.getByRole('combobox', { name: /^Color name/ }).fill('Red')
  await page.getByLabel('Screen color sample').fill('#ff0000')
  await page.getByRole('button', { name: 'Save filament' }).click()
  await expect.poll(() => filamentUpdate?.color_name).toBe('Red')
  await expect.poll(() => filamentUpdate?.color_hex).toBe('FF0000')

  const primaryProfileCard = page.getByRole('heading', { name: '0.4 mm nozzle' }).locator('xpath=ancestor::article')
  await primaryProfileCard.getByRole('button', { name: 'Edit settings' }).click()
  await expect(page.getByText('Customized · Template: 210')).toBeVisible()
  await expect(page.locator('.setting-field--customized')).toHaveCount(2)
  await expect(page.getByLabel('Retraction Retract Speed (mm/s)')).toHaveCount(1)
  await expect(page.getByLabel('Retraction Prime Speed (mm/s)')).toHaveCount(1)
  await expect(page.getByLabel('Maximum fan speed (%)')).toHaveCount(1)
  await expect(page.getByLabel(/^Regular fan speed/)).toHaveAttribute('min', '0')
  await expect(page.getByLabel('Maximum fan speed (%)')).toHaveAttribute('min', '0')
  await expect(page.getByLabel(/^Regular Fan Speed at Layer/)).toHaveAttribute('min', '1')
  await expect(page.getByLabel(/^Minimum Layer Time \(s\)/)).toHaveCount(1)
  await expect(page.getByLabel(/^Minimum Layer Time at Maximum Fan/)).toHaveCount(1)
  await expect(page.getByLabel(/^Minimum Speed/)).toHaveCount(1)
  await expect(page.getByLabel(/^Retraction Speed/)).toHaveCount(0)
  await expect(page.getByLabel(/^Initial Fan Speed/)).toHaveCount(1)
  await expect(page.getByLabel('Printing temperature (°C)')).toHaveCount(1)
  await expect(page.getByLabel('Build volume temperature (°C)')).toHaveCount(1)
  await expect(page.getByLabel('Build plate temperature (°C)')).toHaveCount(1)
  await expect(page.getByLabel(/^Default print temperature/)).toHaveCount(0)
  await page.getByRole('heading', { name: 'Cooling' }).scrollIntoViewIfNeeded()
  await captureEvidence(page, 'filament-profile-cooling')
  await page.getByLabel('Build plate temperature (°C)').fill('61')
  await expect(page.locator('.setting-field--customized')).toHaveCount(3)
  await page.getByLabel('Build plate temperature (°C)').fill('60')
  await expect(page.locator('.setting-field--customized')).toHaveCount(2)
  await page.getByLabel('Printing temperature (°C)').fill('215')
  await page.getByRole('button', { name: 'Save settings' }).click()
  await expect.poll(() => profileUpdate?.expected_profile_version).toBe(1)
  await expect.poll(() => (profileUpdate?.settings as Record<string, unknown>)?.extruder_temp_c).toBe('215')
  await expect.poll(() => (profileUpdate?.settings as Record<string, unknown>)?.pressure_advance).toBe('0.035')
  await expect.poll(() => (profileUpdate?.settings as Record<string, unknown>)?.cura_extensions).toEqual({ xy_offset: '0.05' })
  await page.setViewportSize({ width: 390, height: 844 })
  const secondaryProfileCard = page.getByRole('heading', { name: '0.6 mm nozzle' }).locator('xpath=ancestor::article')
  await expect(secondaryProfileCard.getByRole('button', { name: 'Edit settings' })).toBeVisible()
  await expect(secondaryProfileCard.getByRole('button', { name: 'Compare' })).toBeVisible()
  await expect(secondaryProfileCard.getByRole('link', { name: 'Export Cura JSON' })).toBeVisible()
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
  await expect(page.getByRole('option', { name: /PLA · Blue · Carbon Fiber · Silk/ })).toHaveCount(0)
  await page.getByRole('button', { name: 'Add spool' }).click()
  await expect(page.getByRole('option', { name: /PLA · Blue · Carbon Fiber · Silk/ })).toHaveCount(1)
  await page.getByLabel('Spool code').fill('PLA-BLUE-01')
  await page.getByLabel('Purchase cost').fill('15')
  await expect(page.getByText('1.5¢/g using filament weight only.')).toBeVisible()
  await page.getByRole('button', { name: 'Create spool' }).click()
  await expect.poll(() => submitted?.filament_product_id).toBe(filament.id)
  await expect.poll(() => submitted?.spool_code).toBe('PLA-BLUE-01')
  await expect.poll(() => submitted?.purchase_cost).toBe('15')
})

test('free-text bucket location is editable from Filament Manager', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  let currentSpool = spool
  await page.route('**/api/v1/filaments', (route) => route.fulfill({ json: [filament] }))
  await page.route('**/api/v1/spools?**', (route) => route.fulfill({
    json: { items: [currentSpool], total: 1, limit: 200, offset: 0 },
  }))
  await page.route('**/api/v1/spools/spool-id', async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>
    currentSpool = { ...spool, location: 'Bucket 12', record_version: 4 }
    await route.fulfill({ json: currentSpool })
  })

  await page.goto('/spools')
  await expect(page.getByText('PLA · Blue', { exact: true })).toBeVisible()
  await expect(page.getByText('Carbon Fiber · Silk', { exact: true })).toBeVisible()
  await captureEvidence(page, 'spool-material-identity')
  await expect(page.getByText('1.5¢/g', { exact: true }).first()).toBeVisible()
  await page.getByText('PLA-BLUE-01', { exact: true }).click()
  await expect(page.getByText('Bucket 3', { exact: true }).last()).toBeVisible()
  await page.getByRole('button', { name: 'Edit spool' }).click()
  await page.getByLabel('Bucket or location').fill('Bucket 12')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Save spool' }).click()

  await expect.poll(() => submitted?.expected_version).toBe(3)
  await expect.poll(() => submitted?.location).toBe('Bucket 12')
  await expect(page.getByText('Bucket 12', { exact: true }).last()).toBeVisible()
})

test('an empty Cura library can complete the one-time atomic takeover', async ({ page }) => {
  const agent = {
    id: 'agent-id', agent_code: 'WS-TEST', display_name: 'Arch Cura', hostname: 'workstation',
    platform: 'arch_linux', architecture: 'x86_64', agent_version: '0.2.2', enabled: true,
    cura_management_enabled: false, capabilities: { unmanaged_material_count: 0, unmanaged_import_source_count: 0 },
    cura_installations: [{ installation_id: 'cura-id', version: '5.13', channel: 'Linux Cura', path_hint: 'Linux Cura user data / 5.13', setting_version: 27, managed_library_checksum: null, machines: [] }],
    cura_materials: [], last_seen_at: '2026-08-11T14:00:00Z', last_error: null,
    record_version: 1, created_at: '2026-08-11T12:00:00Z',
  }
  let submitted: Record<string, unknown> | null = null
  await page.route('**/api/v1/workstation-agents', (route) => route.fulfill({ json: [agent] }))
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/workstation-agents/agent-id/cura-takeover', async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ json: { ...agent, cura_management_enabled: true, record_version: 2 } })
  })

  await page.goto('/workstations')
  await expect(page.getByText('Awaiting one-time takeover')).toBeVisible()
  await page.getByRole('button', { name: 'Review empty takeover' }).click()
  let dialog = page.getByRole('dialog', { name: 'Map Cura profiles to templates' })
  await expect(dialog.getByText('No Cura profiles are selectable.')).toBeVisible()
  await dialog.getByRole('button', { name: 'Review takeover (0 mapped)' }).click()
  dialog = page.getByRole('dialog', { name: 'Review Cura takeover' })
  await expect(dialog.getByText('No Cura sources will be imported.')).toBeVisible()
  await dialog.getByRole('button', { name: 'Complete takeover' }).click()
  await expect.poll(() => submitted?.confirmed).toBe(true)
  await expect.poll(() => submitted?.mappings).toEqual([])
})

test('managed Cura workstations show verified material print setting coverage', async ({ page }) => {
  const agent = {
    id: 'agent-id', agent_code: 'WS-TEST', display_name: 'Arch Cura', hostname: 'workstation',
    platform: 'arch_linux', architecture: 'x86_64', agent_version: '0.5.3', enabled: true,
    cura_management_enabled: true,
    capabilities: { managed_material_count: 3, unmanaged_print_profile_count: 0, cura_recovery_snapshots: true },
    cura_installations: [{
      installation_id: 'cura-id', version: '5.13', channel: 'Linux Cura',
      path_hint: 'Linux Cura user data / 5.13', setting_version: 27,
      managed_library_checksum: 'a'.repeat(64), machines: [],
      material_settings_sync: {
        status: 'healthy', expected_count: 53, exposed_count: 53,
        missing_keys: [], unexpected_keys: [],
        material_settings_plugin_ready: true, klipper_settings_plugin_ready: true,
        catalog_checksum: 'b'.repeat(64), verified_at: '2026-08-22T04:00:00Z',
      },
    }],
    cura_materials: [], cura_recovery_status: 'ready', cura_recovery_message: null,
    last_recovery_snapshot_at: '2026-08-22T03:00:00Z', last_recovery_restore_at: null,
    last_seen_at: '2026-08-22T04:00:00Z', last_error: null,
    record_version: 2, created_at: '2026-08-11T12:00:00Z',
  }
  await page.route('**/api/v1/workstation-agents', (route) => route.fulfill({ json: [agent] }))
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/workstation-agents/agent-id/cura-recovery-snapshots?include_compatible=true', (route) => route.fulfill({ json: [{
    id: 'snapshot-id', agent_id: 'agent-id', installation_id: 'cura-id', cura_version: '5.13', setting_version: 27,
    snapshot_checksum: 'c'.repeat(64), file_count: 8, total_bytes: 12000, machine_count: 1,
    quality_profile_count: 3, plugin_count: 1, capture_kind: 'automatic', name: 'Known good Cura setup',
    description: null, record_version: 1, plugins: [], captured_at: '2026-08-22T03:00:00Z', created_at: '2026-08-22T03:00:00Z',
  }] }))
  await page.route('**/api/v1/cura-deployments', (route) => route.fulfill({ json: [{
    id: 'capture-id', agent_id: 'agent-id', material_profile_id: null, requested_by: 'administrator-id',
    operation: 'recovery_capture', status: 'failed', profile_checksum: 'd'.repeat(64), attempts: 1,
    next_attempt_at: '2026-08-22T03:30:00Z', claimed_at: '2026-08-22T03:30:00Z', completed_at: '2026-08-22T03:31:00Z',
    result: {}, last_error_class: 'RuntimeError', last_error_message: 'Backup did not complete safely.',
    created_at: '2026-08-22T03:30:00Z', updated_at: '2026-08-22T03:31:00Z',
  }] }))

  await page.goto('/workstations')
  await expect(page.getByText('53 of 53 verified')).toBeVisible()
  await expect(page.getByText('Material Settings and Klipper Settings are ready; managed values are enforced over Cura profiles.')).toBeVisible()
  await expect(page.getByText(/Verified Aug 22, 2026/)).toBeVisible()
  await page.getByRole('button', { name: 'Recovery points' }).click()
  const recovery = page.getByRole('dialog', { name: 'Recovery points for Arch Cura' })
  const saved = recovery.getByRole('heading', { name: 'Saved Cura configurations' })
  const requests = recovery.getByRole('heading', { name: 'Recent backup requests' })
  await expect(saved).toBeVisible()
  await expect(requests).toBeVisible()
  await expect(recovery.getByText('Known good Cura setup')).toBeVisible()
  expect(await recovery.locator('.editor-section__header h3').allTextContents()).toEqual([
    'Saved Cura configurations',
    'Recent backup requests',
  ])
})

test('each reported Cura source can be mapped to a template or intentionally ignored', async ({ page }) => {
  const material = {
    source_id: 'b'.repeat(64), installation_id: 'cura-id', name: 'Polymaker PETG · PolyLite',
    brand: 'Polymaker', material_type: 'PETG', color_name: 'Black',
    settings: {
      material_print_temperature: '225', material_bed_temperature: '70',
      material_flow: '98.5', klipper_pressure_advance_factor: '0.035',
    },
  }
  const printProfile = {
    source_id: 'd'.repeat(64), installation_id: 'cura-id', name: 'Precision PLA',
    brand: 'Cura print profile', material_type: 'Not assigned', color_name: 'Not applicable',
    source_kind: 'print_profile', machine_name: 'Workshop Printer', quality_type: 'normal',
    omitted_setting_count: 2,
    settings: { speed_print: '72', material_flow: '99', retraction_amount: '0.7' },
  }
  const agent = {
    id: 'agent-id', agent_code: 'WS-TEST', display_name: 'Arch Cura', hostname: 'workstation',
    platform: 'arch_linux', architecture: 'x86_64', agent_version: '0.2.2', enabled: true,
    cura_management_enabled: false,
    capabilities: { unmanaged_material_count: 1, unmanaged_print_profile_count: 1, unmanaged_import_source_count: 2 },
    cura_installations: [{ installation_id: 'cura-id', version: '5.13', channel: 'Linux Cura', path_hint: 'Linux Cura user data / 5.13', setting_version: 27, managed_library_checksum: null, machines: [] }],
    cura_materials: [material, printProfile], last_seen_at: '2026-08-13T14:00:00Z', last_error: null,
    record_version: 1, created_at: '2026-08-13T12:00:00Z',
  }
  let submitted: Record<string, unknown> | null = null
  await page.route('**/api/v1/workstation-agents', (route) => route.fulfill({ json: [agent] }))
  await page.route('**/api/v1/profiles/templates?include_inactive=true', (route) => route.fulfill({ json: [template] }))
  await page.route('**/api/v1/workstation-agents/agent-id/cura-takeover', async (route) => {
    submitted = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ json: { ...agent, cura_management_enabled: true, record_version: 2 } })
  })

  await page.goto('/workstations')
  await expect(page.getByRole('heading', { name: 'Choose what becomes each template' })).toBeVisible()
  await page.getByRole('button', { name: 'Map Cura profiles' }).click()
  let dialog = page.getByRole('dialog', { name: 'Map Cura profiles to templates' })
  await expect(dialog.getByLabel('Template for Polymaker PETG · PolyLite')).toHaveValue('')
  await dialog.getByLabel('Template for Polymaker PETG · PolyLite').selectOption(template.id)
  await expect(dialog.getByText('Saved print profile · Workshop Printer · normal · 3 tracked settings')).toBeVisible()
  await expect(dialog.getByText('2 Cura expressions omitted safely')).toBeVisible()
  await expect(dialog.getByLabel('Template for Precision PLA')).toHaveValue('')
  await dialog.getByRole('button', { name: 'Review takeover (1 mapped)' }).click()
  dialog = page.getByRole('dialog', { name: 'Review Cura takeover' })
  await expect(dialog.getByText('Polymaker PETG · PolyLite')).toBeVisible()
  await expect(dialog.getByText('1 of 2 reported sources will not be imported.')).toBeVisible()
  await dialog.getByRole('button', { name: 'Complete takeover' }).click()

  await expect.poll(() => submitted?.confirmed).toBe(true)
  await expect.poll(() => submitted?.reviewed_source_ids).toEqual([material.source_id, printProfile.source_id])
  await expect.poll(() => submitted?.mappings).toEqual([{ source_id: material.source_id, template_id: template.id }])
})
