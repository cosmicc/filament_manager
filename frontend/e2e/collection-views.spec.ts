import { expect, test } from '@playwright/test'

const user = {
  id: 'administrator-id', username: 'admin', display_name: 'Administrator',
  role: 'administrator', is_active: true, must_change_password: false, record_version: 1,
}

const filament = {
  id: 'filament-id', vendor_id: null, vendor_name: 'Workshop', material_type: 'PLA',
  filler: null, finish: 'Silk', color_name: 'Ocean Blue', color_hex: '2F80A5',
  color_mode: 'solid', color_hexes: ['2F80A5'], product_name: 'Everyday PLA',
  diameter_mm: '1.75', tolerance_mm: '0.02', density_g_cm3: '1.24',
  nominal_net_mass_g: '1000', notes: 'General-purpose workshop filament.',
  material_template_revision_id: 'revision-id', archived: false, color_editable: true, record_version: 1,
}

const spool = {
  id: 'spool-id', spool_code: 'PLA-BLUE-01', filament_product_id: filament.id,
  material_type: 'PLA', filler: null, finish: 'Silk', color_name: 'Ocean Blue',
  color_hex: '2F80A5', color_mode: 'solid', color_hexes: ['2F80A5'], vendor_name: 'Workshop',
  product_name: 'Everyday PLA', nominal_net_mass_g: '1000', tare_mass_g: '205',
  remaining_mass_expected_g: '742', remaining_mass_measured_g: '742', remaining_mass_effective_g: '742',
  remaining_percent: '74.2', weight_confidence: 'measured', status: 'in_stock', purchase_source: 'Local supplier',
  purchase_date: '2026-08-20', purchase_cost: '18.00', cost_per_gram: '0.018', currency: 'USD',
  location: 'Workshop shelf A', spoolman_id: 7, active_printer_id: null,
  last_measurement_at: '2026-08-23T18:00:00Z', notes: null, archived: false,
  record_version: 2, completed_print_count: 8,
}

const printer = {
  id: 'printer-id', printer_code: 'printer-1', name: 'Workshop Printer', nozzle_diameter_mm: '0.4',
  active_plate_id: null, active_plate_surface_id: null, status: 'connected', record_version: 1,
}

const plate = {
  id: 'plate-id', plate_code: 'P1', display_name: 'Textured Workshop Plate', description: 'Double-sided spring steel',
  manufacturer: 'Workshop', product_name: 'PEI Flex', shape: 'rectangular',
  dimensions_mm: { width: '235', depth: '235', thickness: '1.2' }, magnetic: true, flexible: true,
  condition: 'good', status: 'active', preferred_materials: ['PLA', 'PETG'], max_bed_temp_c: '120',
  last_cleaned_at: '2026-08-22T18:00:00Z', cleaning_due_after_prints: 20, cleaning_due_after_days: 14,
  mesh_due_after_prints: 50, mesh_due_after_days: 30, notes: null, image_url: null, image_version: 0,
  record_version: 1, completed_print_count: 14, surfaces: [{
    id: 'surface-id', build_plate_id: 'plate-id', side: 'a', surface_code: 'P1', klipper_mesh_profile: 'P1',
    surface_material: 'PEI', texture: 'textured', mesh_available: true,
    last_mesh_checked_at: '2026-08-23T18:00:00Z', last_mesh_calibrated_at: '2026-08-20T18:00:00Z',
    notes: null, record_version: 1, completed_print_count: 14,
  }],
}

const nozzle = {
  id: 'nozzle-id', nozzle_code: 'N4', diameter_mm: '0.4', material: 'Hardened steel',
  manufacturer: 'Workshop', product_name: 'High-flow', coating: 'Nickel', purchase_date: null,
  status: 'available', printer_id: printer.id, installed_printer_id: null, installed_at: null, retired_at: null,
  notes: null, record_version: 1, completed_print_count: 22, completed_filament_weight_g: '8240.5',
}

test.beforeEach(async ({ page }) => {
  await page.route('**/runtime-config.js', (route) => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/notifications**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/printers', (route) => route.fulfill({ json: [printer] }))
  await page.route('**/api/v1/filaments**', (route) => route.fulfill({ json: [filament] }))
  await page.route('**/api/v1/profiles/templates**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: [{
    id: 'profile-id', filament_product_id: filament.id, extruder_temp_c: '212',
  }] }))
  await page.route('**/api/v1/vendors', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/filament-colors', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/spools?**', (route) => route.fulfill({ json: { items: [spool], total: 1, limit: 200, offset: 0 } }))
  await page.route('**/api/v1/build-plates', (route) => route.fulfill({ json: [plate] }))
  await page.route('**/api/v1/build-plates/maintenance/status', (route) => route.fulfill({ json: [{ build_plate_id: plate.id, cleaning_due: false, cleaning_prints_since: 3, cleaning_due_at: null, surfaces: [] }] }))
  await page.route('**/api/v1/build-plates/maintenance/events**', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/nozzles?include_retired=true', (route) => route.fulfill({ json: [nozzle] }))
})

test('catalog views are independent, remembered, full-width, and action complete', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('filament-manager-theme', 'dark-navy'))
  await page.goto('/spools')
  await expect(page.getByLabel('Spools view')).toHaveValue('list')
  const viewColors = await page.getByLabel('Spools view').evaluate((select) => {
    const option = select.querySelector('option')
    const selectStyle = window.getComputedStyle(select)
    const optionStyle = option ? window.getComputedStyle(option) : null
    return {
      selectColor: selectStyle.color,
      selectBackground: selectStyle.backgroundColor,
      optionColor: optionStyle?.color,
      optionBackground: optionStyle?.backgroundColor,
    }
  })
  expect(viewColors.selectColor).not.toBe('rgb(255, 255, 255)')
  expect(viewColors.selectBackground).not.toBe('rgba(0, 0, 0, 0)')
  expect(viewColors.optionColor).toBe(viewColors.selectColor)
  expect(viewColors.optionBackground).not.toBe('rgb(255, 255, 255)')
  await expect(page.locator('.inventory-layout')).toHaveCount(0)
  await expect(page.getByText('Select a spool')).toHaveCount(0)
  await page.getByLabel('Spools view').selectOption('detailed')
  await page.reload()
  await expect(page.getByLabel('Spools view')).toHaveValue('detailed')
  await page.getByRole('button', { name: /PLA-BLUE-01/ }).click()
  await expect(page.getByRole('dialog', { name: 'PLA-BLUE-01 details' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Weigh spool' })).toBeVisible()
  await page.getByRole('button', { name: 'Done' }).click()
  await page.screenshot({ path: '../docs/design/validation/inventory-views-v041.png', fullPage: true })

  await page.goto('/filaments')
  await expect(page.getByLabel('Filaments view')).toHaveValue('cards')
  await expect(page.getByRole('heading', { name: 'PLA · Ocean Blue · Silk' })).toBeVisible()
  await expect(page.getByText('No filler')).toHaveCount(0)
  await expect(page.getByText('± 0.02 mm')).toBeVisible()
  await expect(page.getByText('212 °C')).toBeVisible()
  await expect(page.getByText('1.75 mm')).toHaveCount(0)
  await expect(page.getByText('1,000 g')).toHaveCount(0)
  await page.getByLabel('Filaments view').selectOption('list')
  await page.reload()
  await expect(page.getByLabel('Filaments view')).toHaveValue('list')

  await page.goto('/plates')
  await expect(page.getByLabel('Build plates view')).toHaveValue('detailed')
  await page.getByLabel('Build plates view').selectOption('cards')
  await page.locator('.collection-card--button').click()
  await expect(page.getByRole('dialog', { name: 'P1 details' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit physical plate' })).toBeVisible()
  await page.getByRole('button', { name: 'Done' }).click()

  await page.goto('/nozzles')
  await expect(page.getByLabel('Nozzles view')).toHaveValue('cards')
  await page.locator('.collection-card--button').click()
  await expect(page.getByRole('dialog', { name: 'N4 details' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'History' })).toBeVisible()
  await page.getByRole('button', { name: 'Done' }).click()

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/spools')
  await page.getByLabel('Spools view').selectOption('cards')
  await expect(page.locator('.collection-card--button')).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/inventory-views-mobile-v041.png', fullPage: true })
})
