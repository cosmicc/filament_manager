import { expect, test } from '@playwright/test'
import type { Spool } from '../src/api/types'

const printerState = {
  printer_name: 'Workshop Printer',
  connection_status: 'connected',
  operational_status: 'idle',
  klipper_state: 'ready',
  print_state: 'standby',
  filename: null,
  progress_percent: null,
  nozzle_temperature_c: '24',
  nozzle_target_c: '0',
  bed_temperature_c: '23',
  bed_target_c: '0',
  chamber_temperature_c: null,
  chamber_target_c: null,
  print_job_id: null,
  thumbnail_url: null,
  estimated_duration_seconds: null,
  print_duration_seconds: null,
  predicted_filament_weight_g: null,
  actual_filament_weight_g: null,
  actual_filament_cost: null,
  predicted_filament_cost: null,
  cost_currency: null,
  cost_complete: false,
  checked_at: '2026-08-27T20:00:00Z',
}

test('dashboard replaces its rendered operational snapshot within ten seconds', async ({ page }) => {
  let dashboardRequests = 0
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const json = path.endsWith('/auth/me')
      ? { id: 'admin-id', username: 'admin', display_name: 'Administrator', role: 'administrator', is_active: true, must_change_password: false, record_version: 1 }
      : path.endsWith('/notifications')
        ? []
        : path.endsWith('/dashboard')
          ? (++dashboardRequests === 1
              ? {
                  total_spools: 8,
                  material_spool_counts: { PLA: 8 },
                  distinct_colors: 2,
                  needs_weighing: 1,
                  low_spools: 0,
                  empty_spools: 0,
                  active_spool: null,
                  active_plate: null,
                  active_plate_surface: null,
                  printer_state: printerState,
                }
              : {
                  total_spools: 9,
                  material_spool_counts: { PLA: 8, PETG: 1 },
                  distinct_colors: 3,
                  needs_weighing: 1,
                  low_spools: 0,
                  empty_spools: 0,
                  active_spool: {
                    id: 'spool-live',
                    filament_product_id: 'filament-live',
                    spool_code: 'S009',
                    status: 'active',
                    vendor_name: 'Polymaker',
                    material_type: 'PLA',
                    color_name: 'Blue',
                    color_mode: 'solid',
                    color_hexes: ['#2457A6'],
                    color_hex: '#2457A6',
                    remaining_mass_effective_g: '750',
                    remaining_percent: '75',
                    weight_confidence: 'high',
                  },
                  active_plate: {
                    plate_code: 'P2',
                    display_name: 'Smooth PEI',
                    image_url: null,
                    condition: 'good',
                  },
                  active_plate_surface: {
                    surface_code: 'P2',
                    side: 'a',
                    surface_material: 'PEI',
                  },
                  printer_state: {
                    ...printerState,
                    operational_status: 'paused',
                    print_state: 'paused',
                    filename: 'updated-part.gcode',
                    progress_percent: '51',
                  },
                })
          : []
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(json) })
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Workshop Printer' })).toBeVisible()
  await expect(page.getByText('No active spool')).toBeVisible()

  await expect(page.getByText('updated-part.gcode')).toBeVisible({ timeout: 12_000 })
  await expect(page.getByText('S009')).toBeVisible()
  await expect(page.getByText('Smooth PEI')).toBeVisible()
  await expect(page.getByText('9', { exact: true })).toBeVisible()
  expect(dashboardRequests).toBeGreaterThanOrEqual(2)
  const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
  if (evidence) await page.screenshot({ path: `${evidence}/dashboard-active-desktop-v083.png`, fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  if (evidence) await page.screenshot({ path: `${evidence}/dashboard-active-mobile-v083.png`, fullPage: true })
})

for (const activeRating of [3, 0]) {
  test(`active spool card navigation and readable ${activeRating === 0 ? 'blocked' : 'better-plate'} warning`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (['error', 'warning'].includes(message.type())) errors.push(message.text()) })
    const spool: Spool = {
      id: 'spool-one', spool_code: 'P1', filament_product_id: 'filament-one', vendor_name: 'Workshop',
      material_type: 'PLA', color_name: 'Blue', filler: 'None', finish: 'Standard', color_mode: 'solid', color_hex: '2457A6', color_hexes: ['2457A6'],
      remaining_mass_effective_g: '750', remaining_percent: '75', nominal_net_mass_g: '1000', tare_mass_g: '200', weight_confidence: 'measured',
      status: 'in_stock', active_printer_id: 'printer-one', active_extruder: 'extruder', record_version: 1, archived: false, completed_print_count: 0,
      product_name: null, remaining_mass_expected_g: '750', remaining_mass_measured_g: '750',
      purchase_source: null, purchase_date: null, purchase_cost: null, cost_per_gram: null, currency: 'USD',
      location: null, spoolman_id: null, last_measurement_at: null, notes: null,
    }
    const secondSpool = { ...spool, id: 'spool-two', spool_code: 'P2', active_extruder: 'extruder1' }
    const plates = [
      { id: 'plate-one', plate_code: 'P1', display_name: 'Smooth PEI', status: 'active', surfaces: [] },
      { id: 'plate-two', plate_code: 'P2', display_name: 'Textured PEI', status: 'active', surfaces: [] },
    ]
    let multiple = false
    const detailReads: string[] = []
    await page.addInitScript(() => localStorage.setItem('filament-manager-theme', 'dark-navy'))
    await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
      let json: unknown = []
      if (path === '/auth/me') json = { id: 'admin', username: 'admin', role: 'administrator', is_active: true, must_change_password: false }
      else if (path === '/dashboard') json = {
        total_spools: 2, material_spool_counts: { PLA: 2 }, distinct_colors: 1, needs_weighing: 0, low_spools: 0, empty_spools: 0,
        active_spool: spool, active_plate: plates[0], active_plate_surface: null, printer_state: printerState,
        printer_contexts: [{ printer_id: 'printer-one', printer_state: printerState, active_spools: multiple ? [spool, secondSpool] : [spool], active_plate: plates[0], active_plate_surface: null }],
      }
      else if (path === '/build-plates') json = plates
      else if (path === '/build-plate-ratings/filament/filament-one') json = [{
        printer_id: 'printer-one', printer_name: printerState.printer_name, template_id: 'template-one', template_name: 'Template PLA',
        active_plate_id: 'plate-one', inherited_ratings: { 'plate-one': activeRating, 'plate-two': 5 },
        ratings: { 'plate-one': activeRating, 'plate-two': 5 }, overrides: {}, record_version: 1,
      }]
      else if (path.endsWith('/overrides')) json = { record_version: 1, ratings: {} }
      else if (path === '/spools') json = { items: [spool, secondSpool], total: 2, limit: 200, offset: 0 }
      else if (path === '/spools/spool-one' || path === '/spools/spool-two') {
        detailReads.push(path)
        json = path.endsWith('spool-one') ? spool : secondSpool
      }
      else if (path.startsWith('/prints/activity/')) json = {}
      await route.fulfill({ json })
    })

    await page.goto('/')
    await expect(page).toHaveTitle('Filament Manager')
    await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible()
    const card = page.locator('.active-spool-card--active')
    await expect(card.getByText('View inventory')).toHaveCount(0)
    const alert = card.getByRole('alert')
    await expect(alert).toContainText(activeRating === 0 ? 'Do NOT use this build plate' : 'A better-rated build plate is available.')
    await expect(alert.locator('small').first()).toHaveCSS('font-size', '16px')
    await expect(alert.locator('strong')).toHaveCSS('font-size', '18px')
    await card.getByRole('button', { name: '★ View all build plate ratings', exact: true }).click()
    const ratingDialog = page.getByRole('dialog', { name: 'Filament build plate ratings', exact: true })
    await expect(ratingDialog).toBeVisible()
    await expect(page).toHaveURL(/\/$/)
    await ratingDialog.getByRole('button', { name: 'Done', exact: true }).click()
    const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
    await card.scrollIntoViewIfNeeded()
    if (evidence) await page.screenshot({ path: `${evidence}/dashboard-spool-warning-${activeRating}-desktop-v085.png` })
    // Hit the card padding rather than the spool name to verify the full-card link.
    await card.click({ position: { x: 8, y: 8 } })
    await expect(page.getByRole('dialog', { name: 'P1 details', exact: true })).toBeVisible()
    expect(detailReads).toContain('/spools/spool-one')

    await page.goto('/')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => { document.documentElement.dataset.theme = 'light-navy' })
    await card.scrollIntoViewIfNeeded()
    await expect.poll(() => card.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true)
    await expect(page.locator('vite-error-overlay')).toHaveCount(0)
    if (evidence) await page.screenshot({ path: `${evidence}/dashboard-spool-warning-${activeRating}-mobile-v085.png` })
    const link = card.getByRole('link', { name: 'Open spool P1 details' })
    await link.focus()
    await expect(link).toBeFocused()
    await link.press('Enter')
    await expect(page.getByRole('dialog', { name: 'P1 details', exact: true })).toBeVisible()

    multiple = true
    await page.goto('/')
    await expect(card.getByRole('link', { name: 'Open spool P2 details' })).toHaveAttribute('href', '/spools?spool_id=spool-two')
    await card.locator('.active-spool').nth(1).click({ position: { x: 4, y: 4 } })
    await expect(page.getByRole('dialog', { name: 'P2 details', exact: true })).toBeVisible()
    expect(detailReads).toContain('/spools/spool-two')
    expect(errors).toEqual([])
  })
}
