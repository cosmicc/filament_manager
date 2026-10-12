import { expect, test } from '@playwright/test'

const user = {
  id: 'administrator-id', username: 'admin', display_name: 'Administrator',
  role: 'administrator', is_active: true, must_change_password: false, record_version: 1,
}

const filament = {
  id: '12345678-1234-1234-1234-123456789012', vendor_id: null, vendor_name: 'Workshop', material_type: 'PLA',
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

const rigid = { ...filament, id: 'rigid-id', color_name: 'Rigid White', color_hex: 'FFFFFF', color_hexes: ['FFFFFF'] }
const unknown = { ...filament, id: 'unknown-id', color_name: 'Unknown Black' }
const settings = {
  extruder_temp_c: '212', bed_temp_c: '60', initial_bed_temp_c: '60', flow_percent: '100',
  cooling_min_percent: '0', cooling_max_percent: '100', filament_density_g_cm3: '1.24',
  drying_temp_c: '55', drying_time_hours: '6-8', moisture_sensitivity: 'high', cura_extensions: {},
  shore_hardness: { scale: 'A', value: '95' },
}
const template = {
  id: 'template-id', name: 'Template PLA', material_type: 'PLA', printer_id: 'printer-id',
  nozzle_id: 'nozzle-id', nozzle_diameter_mm: '0.4', filament_diameter_mm: '1.75', active: true,
  record_version: 1, description: null, revisions: [{ id: 'revision-id', version: 1, settings }],
}

for (const mobile of [false, true]) {
  test(`0.9.2 hardness and care flow ${mobile ? 'mobile' : 'desktop'}`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => { if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text()) })
    await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 })
    await page.addInitScript((theme) => localStorage.setItem('filament-manager-theme', theme), mobile ? 'light' : 'dark-navy')
    await page.route('**/runtime-config.js', (route) => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', (route) => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
      let json: unknown = []
      if (path === '/auth/me') json = user
      else if (path === '/filaments') json = [rigid, unknown, filament]
      else if (path === `/filaments/${filament.id}`) json = filament
      else if (path === '/profiles') json = [
        { ...settings, id: 'profile-id', filament_product_id: filament.id, printer_id: 'printer-id', base_template_id: template.id, base_template_revision_id: 'revision-id', base_template_settings: settings, override_keys: [], override_count: 0, record_version: 1, cura_settings: {}, nozzle_diameter_mm: '0.4', base_template_name: 'Template PLA' },
        { ...settings, id: 'rigid-profile-id', filament_product_id: rigid.id, shore_hardness: { scale: 'D', value: '75' } },
      ]
      else if (path.startsWith('/profiles/templates')) json = path === '/profiles/templates' ? [template] : template
      else if (path === '/spools') json = { items: [spool], total: 1, limit: 200, offset: 0 }
      else if (path === '/printers') json = [{ id: 'printer-id', name: 'Workshop printer', nozzle_diameter_mm: '0.4' }]
      else if (path === '/nozzles') json = [{ id: 'nozzle-id', printer_id: 'printer-id', nozzle_code: 'N4', diameter_mm: '0.4', material: 'Brass', status: 'installed' }]
      else if (path.startsWith('/build-plate-ratings/filament/')) json = []
      else if (path.startsWith('/build-plate-ratings/')) json = { ratings: {}, record_version: 1 }
      return route.fulfill({ json })
    })
    await page.goto('/filaments')
    await expect(page).toHaveTitle('Filament Manager')
    await expect(page.getByRole('heading', { name: 'Filaments', exact: true })).toBeVisible()
    await page.getByLabel('Sort filaments').selectOption('softest')
    await expect(page.locator('.catalog-card h2')).toHaveText(['PLA · Ocean Blue · Silk', 'PLA · Rigid White · Silk', 'PLA · Unknown Black · Silk'])
    await expect(page.locator('.catalog-card').first()).toContainText('95A (≈46D)')
    await page.getByLabel('Sort filaments').selectOption('hardest')
    await expect(page.locator('.catalog-card h2')).toHaveText(['PLA · Rigid White · Silk', 'PLA · Ocean Blue · Silk', 'PLA · Unknown Black · Silk'])
    await page.getByLabel('Filaments view').selectOption('detailed')
    await expect(page.locator('.catalog-card').first()).toContainText('Density')
    await expect(page.getByText('Color changes', { exact: true })).toHaveCount(0)
    await page.getByLabel('Filaments view').selectOption('list')
    await expect(page.getByRole('columnheader', { name: 'Shore hardness', includeHidden: true })).toHaveCount(1)
    await expect(page.getByRole('columnheader', { name: 'Diameter' })).toHaveCount(0)
    await page.getByRole('button', { name: 'Shore hardness reference' }).click()
    const reference = page.getByRole('dialog', { name: 'Shore hardness reference' })
    await expect(reference.getByRole('table')).toHaveCount(2)
    await expect(reference).toContainText('95A')
    await expect(reference).toContainText('≈46D')
    await expect(reference.getByRole('columnheader', { name: 'Shore A', exact: true })).toBeVisible()
    expect(await reference.locator('caption').first().evaluate((element) => element.getBoundingClientRect().width > 200)).toBeTruthy()
    await page.screenshot({ path: `/tmp/hardness-reference-${mobile ? 'mobile' : 'desktop'}.png` })
    await page.keyboard.press('Escape')
    await expect(reference).toHaveCount(0)

    await page.goto(`/filaments/${filament.id}`)
    await expect(page.getByRole('heading', { name: 'Product details', exact: true })).toBeVisible()
    await expect(page.locator('.product-editor')).toContainText('95A (≈46D)')
    await page.getByRole('button', { name: 'Edit settings', exact: true }).click()
    const profileEditor = page.getByRole('dialog', { name: /Edit Workshop printer/ })
    await profileEditor.getByLabel('Shore hardness value').fill('98')
    await expect(profileEditor).toContainText('98A (≈53D)')
    await profileEditor.getByRole('button', { name: 'Revert to Template' }).click()
    await expect(profileEditor.getByLabel('Shore hardness value')).toHaveValue('95')
    await page.keyboard.press('Escape')

    await page.goto('/templates')
    await expect(page.getByRole('heading', { name: 'Template PLA', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Edit Template PLA', exact: true }).click()
    await expect(page.getByLabel('Shore hardness value')).toHaveValue('95')
    await page.getByLabel('Shore hardness scale').selectOption('D')
    await page.getByLabel('Shore hardness value').fill('75')
    await expect(page.getByLabel('Shore hardness value')).toHaveValue('75')
    await page.keyboard.press('Escape')

    await page.goto('/spools')
    await page.getByLabel('Spools view').selectOption('detailed')
    const card = page.locator('.collection-card--button')
    await expect(card).toContainText('95A (≈46D)')
    await expect(card.getByText('Printer', { exact: true })).toHaveCount(0)
    await card.click()
    const details = page.getByRole('dialog', { name: 'PLA-BLUE-01 details' })
    const care = details.getByRole('region', { name: 'Filament care and hardness' })
    await expect(care).toContainText('55 °C')
    await expect(care).toContainText('6-8 hours')
    await expect(care).toContainText('High')
    await expect(care).toContainText('95A (≈46D)')
    await expect(details.getByText('Printer assignment', { exact: true })).toBeVisible()
    await care.getByRole('button', { name: 'Shore hardness reference' }).click()
    await expect(page.getByRole('dialog', { name: 'Shore hardness reference' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(details).toBeVisible()
    await page.screenshot({ path: `/tmp/spool-care-${mobile ? 'mobile' : 'desktop'}.png` })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    expect(errors).toEqual([])
  })
}
