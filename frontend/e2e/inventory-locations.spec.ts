import { expect, test } from '@playwright/test'

const productId = '83bc4b7e-e7ad-420e-8324-900b06c099bb'
const spoolId = '61b4cc21-b55e-4b56-9b22-5bd514f46891'
const filament = {
  id: productId, vendor_id: 'vendor-id', vendor_name: 'Workshop', material_type: 'PLA',
  color_name: 'Blue', color_hex: '2244AA', color_mode: 'solid', color_hexes: ['2244AA'],
  filler: 'Carbon fiber', finish: 'Matte', diameter_mm: '1.75', density_g_cm3: '1.24',
  nominal_net_mass_g: '1000', material_template_revision_id: null, archived: false, record_version: 1,
}
const originalSpool = {
  ...filament, id: spoolId, filament_product_id: productId, spool_code: 'SPOOL-001',
  tare_mass_g: '200', remaining_mass_effective_g: '875', remaining_mass_expected_g: '875',
  remaining_mass_measured_g: '1000', remaining_percent: '87.5', current_total_mass_g: '1075',
  location: 'Bucket 12', status: 'in_stock', weight_confidence: 'measured',
  last_measurement_at: '2026-09-05T00:00:00Z', completed_print_count: 2,
  purchase_cost: '20', cost_per_gram: '0.02', currency: 'USD', active_printer_id: null,
  spoolman_id: 7, notes: null, purchase_source: null, purchase_date: null,
}

for (const variant of [
  { name: 'desktop-dark', viewport: { width: 1440, height: 1050 }, theme: 'dark-navy' },
  { name: 'mobile-light', viewport: { width: 390, height: 844 }, theme: 'light-navy' },
]) {
  test(`Locations, filters, and tare recalculation: ${variant.name}`, async ({ page }) => {
    await page.setViewportSize(variant.viewport)
    await page.addInitScript((theme) => localStorage.setItem('filament-manager-theme', theme), variant.theme)
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
    let spool = { ...originalSpool }
    let patch: Record<string, unknown> | undefined
    let created: Record<string, unknown> | undefined
    const locations = [{ name: 'Bucket 12' }, { name: 'Archived shelf' }]
    await page.route('**/runtime-config.js', (route) => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname.replace('/api/v1', '')
      const method = route.request().method()
      if (path === '/auth/me') return route.fulfill({ json: { id: 'administrator', role: 'administrator', username: 'admin', display_name: 'Administrator', is_active: true, must_change_password: false, record_version: 1 } })
      if (['/notifications', '/printers', '/profiles', '/vendors', '/filament-colors'].includes(path)) return route.fulfill({ json: [] })
      if (path === '/profiles/templates') return route.fulfill({ json: [
        { id: 'template-pla', material_type: 'PLA', revisions: [], active: true },
        { id: 'template-petg', material_type: 'PETG', revisions: [], active: true },
        { id: 'template-pla-2', material_type: 'PLA', revisions: [], active: true },
      ] })
      if (path === '/filaments') return route.fulfill({ json: url.searchParams.get('material') === 'petg' ? [] : [filament] })
      if (path === '/locations') return route.fulfill({ json: [
        { location: 'Bucket 12', spool_count: 1, remaining_mass_g: spool.remaining_mass_effective_g },
        { location: null, spool_count: 1, remaining_mass_g: '500' },
      ] })
      if (path === '/spool-location-choices') {
        if (method === 'POST') {
          const item = route.request().postDataJSON() as { name: string }
          locations.push(item)
          return route.fulfill({ status: 201, json: item })
        }
        return route.fulfill({ json: locations })
      }
      if (path === '/spool-tare-suggestions') return route.fulfill({ json: [
        { tare_mass_g: '250', nominal_net_mass_g: '1000', spool_count: 4 },
        { tare_mass_g: '100', nominal_net_mass_g: '500', spool_count: 2 },
      ] })
      if (path === `/spools/${spoolId}/mass-basis`) return route.fulfill({ json: { last_gross_mass_g: '1200', adjustment_since_weighing_g: '-125' } })
      if (path === `/spools/${spoolId}`) {
        if (method === 'PATCH') {
          patch = route.request().postDataJSON()
          const tare = Number(patch?.tare_mass_g)
          spool = { ...spool, tare_mass_g: String(tare), remaining_mass_effective_g: String(1200 - tare - 125), record_version: spool.record_version + 1 }
        }
        return route.fulfill({ json: spool })
      }
      if (path === '/spools') {
        if (method === 'POST') { created = route.request().postDataJSON(); return route.fulfill({ status: 201, json: spool }) }
        const items = url.searchParams.get('material') === 'petg' || url.searchParams.get('unassigned') === 'true' ? [] : [spool]
        return route.fulfill({ json: { items, total: items.length, limit: 200, offset: 0 } })
      }
      errors.push(`Unexpected API request: ${method} ${path}`)
      return route.fulfill({ status: 500, json: { message: 'Unexpected test request' } })
    })

    await page.goto('/locations')
    await expect(page).toHaveTitle(/Filament Manager/)
    await expect(page.getByRole('heading', { name: 'Locations', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: /Bucket 12.*Spools.*1/ })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: /Unassigned/ })).toBeVisible()
    const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
    if (evidence) await page.screenshot({ path: `${evidence}/locations-${variant.name}.png`, fullPage: true })
    await page.getByRole('button', { name: /SPOOL-001.*Open spool details/ }).click()
    await expect(page).toHaveURL(/\/spools$/)
    await expect(page.getByRole('dialog', { name: 'SPOOL-001 details' })).toBeVisible()
    await page.getByRole('button', { name: 'Edit spool', exact: true }).click()
    const editor = page.getByRole('dialog', { name: 'Edit SPOOL-001' })
    await expect(editor.getByLabel('Current filament remaining (g)', { exact: false })).toHaveValue('875')
    await expect(editor.getByLabel('Current total spool weight (g)', { exact: false })).toHaveAttribute('readonly', '')
    await editor.getByLabel('Suggested empty-spool weight').selectOption('0')
    await expect(editor.getByLabel('Empty spool weight (g)', { exact: false })).toHaveValue('250')
    await expect(editor.getByLabel('Current filament remaining (g)', { exact: false })).toHaveValue('825')
    await expect(editor.getByLabel('Current total spool weight (g)', { exact: false })).toHaveValue('1075')
    await expect(editor.getByLabel('Location', { exact: true })).toHaveValue('Bucket 12')
    await expect(editor.getByLabel('Location', { exact: true }).locator('option').last()).toHaveText('New Location')
    if (evidence) await page.screenshot({ path: `${evidence}/tare-${variant.name}.png`, fullPage: false })
    await editor.getByRole('button', { name: 'Save spool' }).click()
    await expect(page.getByRole('dialog', { name: 'SPOOL-001 details' })).toBeVisible()
    expect(patch?.tare_mass_g).toBe('250')
    expect(patch).not.toHaveProperty('remaining_mass_g')
    expect(patch).not.toHaveProperty('current_total_mass_g')
    await page.getByRole('button', { name: 'Done', exact: true }).click()
    await expect(page.getByLabel('Filter by filament type').locator('option')).toHaveCount(3)
    await page.getByLabel('Filter by filament type').selectOption('petg')
    await expect(page.getByRole('heading', { name: 'No spools found' })).toBeVisible()
    await page.getByLabel('Filter by filament type').selectOption('')
    await expect(page.getByText('SPOOL-001', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Add spool', exact: true }).click()
    const create = page.getByRole('dialog', { name: 'Add a physical spool' })
    await create.getByLabel('Spool code', { exact: true }).fill('NEW-USED')
    await create.getByText('This spool is unused', { exact: false }).click()
    await create.getByLabel('Full spool scale weight (g)', { exact: false }).fill('700')
    await create.getByLabel('Suggested empty-spool weight').selectOption('0')
    await expect(create.getByLabel('Empty spool weight (g)', { exact: false })).toHaveValue('250')
    await create.getByLabel('Location', { exact: true }).selectOption({ label: 'New Location' })
    const newLocation = page.getByRole('dialog', { name: 'New Location', exact: true })
    await expect(newLocation.getByLabel('Location name')).toHaveAttribute('placeholder', 'Bucket 12')
    await newLocation.getByLabel('Location name').fill('Unused storage shelf')
    if (evidence) await page.screenshot({ path: `${evidence}/new-location-${variant.name}.png` })
    await newLocation.getByRole('button', { name: 'Add location' }).click()
    await expect(create.getByLabel('Location', { exact: true })).toHaveValue('Unused storage shelf')
    await expect(create.getByLabel('Spool code', { exact: true })).toHaveValue('NEW-USED')
    await expect(create.getByLabel('Full spool scale weight (g)', { exact: false })).toHaveValue('700')
    await create.getByLabel('Location', { exact: true }).selectOption({ label: 'New Location' })
    await newLocation.getByRole('button', { name: 'Cancel' }).click()
    await expect(create.getByLabel('Location', { exact: true })).toHaveValue('Unused storage shelf')
    if (evidence) await page.screenshot({ path: `${evidence}/spool-location-selected-${variant.name}.png` })
    await create.getByRole('button', { name: /Create spool/ }).click()
    await expect(create).not.toBeVisible()
    expect(created?.initial_gross_mass_g).toBe('700')
    expect(created?.location).toBe('Unused storage shelf')
    await page.getByRole('button', { name: 'Add spool', exact: true }).click()
    await expect(create.getByLabel('Location', { exact: true }).getByRole('option', { name: 'Unused storage shelf' })).toHaveCount(1)
    await create.getByRole('button', { name: 'Cancel', exact: true }).click()
    expect(created?.tare_mass_g).toBe('250')
    expect(created?.infer_tare_from_unused_spool).toBe(false)
    await page.goto('/filaments')
    await expect(page.getByLabel('Filter by filament type')).toHaveValue('')
    await page.getByLabel('Filter by filament type').selectOption('petg')
    await expect(page.getByRole('heading', { name: 'No filament products' })).toBeVisible()
    await page.getByLabel('Filter by filament type').selectOption('pla')
    await expect(page.getByRole('heading', { name: 'PLA · Blue · Carbon fiber · Matte' })).toBeVisible()
    await page.getByLabel('Search filaments').fill('Carbon fiber')
    await expect(page.getByRole('heading', { name: 'PLA · Blue · Carbon fiber · Matte' })).toBeVisible()
    if (evidence) await page.screenshot({ path: `${evidence}/material-filter-${variant.name}.png`, fullPage: false })
    expect(await page.locator('vite-error-overlay').count()).toBe(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect(errors).toEqual([])
  })
}
