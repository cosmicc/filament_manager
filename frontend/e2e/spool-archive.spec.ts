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
  spool_type: 'Cardboard',
  ...filament, id: spoolId, filament_product_id: productId, spool_code: 'SPOOL-001',
  tare_mass_g: '200', remaining_mass_effective_g: '875', remaining_mass_expected_g: '875',
  remaining_mass_measured_g: '1000', remaining_percent: '87.5', current_total_mass_g: '1075',
  location: 'Bucket 12', status: 'in_stock', weight_confidence: 'measured',
  last_measurement_at: '2026-09-05T00:00:00Z', completed_print_count: 2,
  purchase_cost: '20', cost_per_gram: '0.02', currency: 'USD', active_printer_id: null,
  spoolman_id: 7, notes: null, purchase_source: null, purchase_date: null,
}

// These browser fixtures exercise archive browsing; PostgreSQL tests prove persistence.
for (const variant of [
  { name: 'desktop-dark', viewport: { width: 1440, height: 1050 }, theme: 'dark-navy' },
  { name: 'mobile-light', viewport: { width: 390, height: 844 }, theme: 'light-navy' },
]) {
  test(`Spool archive browsing: ${variant.name}`, async ({ page }) => {
    await page.setViewportSize(variant.viewport)
    await page.addInitScript((theme) => localStorage.setItem('filament-manager-theme', theme), variant.theme)
    const errors: string[] = []
    const queries: URL[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
    await page.route('**/runtime-config.js', (route) => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname.replace('/api/v1', '')
      if (path === '/auth/me') return route.fulfill({ json: { id: 'administrator', role: 'administrator', username: 'admin', display_name: 'Administrator', is_active: true, must_change_password: false, record_version: 1 } })
      if (path === '/filaments') return route.fulfill({ json: [filament] })
      if (path === '/spools') {
        queries.push(url)
        const archived = url.searchParams.get('archived_only') === 'true'
        const spool = archived ? { ...originalSpool, spool_code: 'SPOOL-OLD', archived: true, status: 'archived', remaining_mass_effective_g: '0', remaining_percent: '0' } : originalSpool
        const items = url.searchParams.get('material') === 'petg' ? [] : [spool]
        return route.fulfill({ json: { items, total: items.length, limit: 200, offset: 0 } })
      }
      if (path === '/profiles/templates') return route.fulfill({ json: [
        { id: 'template-pla', material_type: 'PLA', revisions: [], active: true },
        { id: 'template-petg', material_type: 'PETG', revisions: [], active: true },
      ] })
      if (path.startsWith('/prints/activity/')) return route.fulfill({ json: {} })
      if (['/notifications', '/profiles', '/printers', '/build-plates', `/build-plate-ratings/filament/${productId}`].includes(path)) return route.fulfill({ json: [] })
      errors.push(`Unexpected API request: ${path}`)
      return route.fulfill({ status: 500, json: { message: 'Unexpected test request' } })
    })
    await page.goto('/spools')
    await expect(page).toHaveTitle(/Filament Manager/)
    await expect(page.getByRole('heading', { name: 'Spools', exact: true })).toBeVisible()
    await expect(page.getByText('SPOOL-001', { exact: true })).toBeVisible()
    await page.getByLabel('Filter by status').selectOption('low')
    await page.getByLabel('Spool inventory').selectOption('archived')
    await expect(page.getByText('SPOOL-OLD', { exact: true })).toBeVisible()
    await expect(page.getByText('SPOOL-001', { exact: true })).toHaveCount(0)
    await expect(page.getByLabel('Filter by status')).toHaveCount(0)
    const archiveQuery = queries.filter((url) => url.searchParams.get('archived_only') === 'true').at(-1)
    expect(archiveQuery?.searchParams.has('status')).toBe(false)
    const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
    for (const view of ['cards', 'detailed']) {
      await page.getByLabel('Spools view').selectOption(view)
      await expect(page.locator('.collection-card .filament-swatch')).toHaveCSS('width', '64px')
      await expect(page.locator('.collection-card .filament-swatch')).toHaveCSS('height', '64px')
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      if (evidence) await page.screenshot({ path: `${evidence}/archive-${view}-${variant.name}.png`, fullPage: false })
    }
    await page.getByText('SPOOL-OLD', { exact: true }).click()
    await expect(page.getByRole('dialog', { name: 'SPOOL-OLD details' })).toBeVisible()
    await page.getByRole('button', { name: 'Done', exact: true }).click()
    await page.getByLabel('Filter by filament type').selectOption('petg')
    await expect(page.getByRole('heading', { name: 'No archived spools found' })).toBeVisible()
    await page.getByLabel('Filter by filament type').selectOption('')
    await page.getByLabel('Spool inventory').selectOption('active')
    await expect(page.getByLabel('Filter by status')).toHaveValue('')
    await expect(page.getByText('SPOOL-001', { exact: true })).toBeVisible()
    await expect(page.getByText('SPOOL-OLD', { exact: true })).toHaveCount(0)
    await page.getByLabel('Spools view').selectOption('list')
    expect(await page.locator('vite-error-overlay').count()).toBe(0)
    expect(errors).toEqual([])
  })
}
