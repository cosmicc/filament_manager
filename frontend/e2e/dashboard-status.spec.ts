import { expect, test, type Page } from '@playwright/test'

const thumbnailSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300"><defs><linearGradient id="background" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0c2238"/><stop offset="1" stop-color="#17607b"/></linearGradient></defs><rect width="400" height="300" rx="18" fill="url(#background)"/><path d="M200 62 294 114v92l-94 52-94-52v-92z" fill="#d8edf5" stroke="#77c8e4" stroke-width="8"/><path d="m106 114 94 54 94-54M200 168v90" fill="none" stroke="#17607b" stroke-width="8"/><text x="200" y="38" fill="#fff" font-family="sans-serif" font-size="18" text-anchor="middle">G-code preview</text></svg>`

const dashboard = {
  total_spools: 18,
  needs_weighing: 2,
  low_spools: 1,
  empty_spools: 0,
  active_spool: null,
  active_plate: null,
  active_plate_surface: null,
  printer_state: {
    printer_name: 'IPLT-Max',
    connection_status: 'connected',
    operational_status: 'printing',
    klipper_state: 'ready',
    print_state: 'printing',
    filename: 'functional-part.gcode',
    progress_percent: '64.2',
    nozzle_temperature_c: '219.7',
    nozzle_target_c: '220',
    bed_temperature_c: '59.8',
    bed_target_c: '60',
    chamber_temperature_c: '38.4',
    chamber_target_c: null,
    print_job_id: '20000000-0000-0000-0000-000000000001',
    thumbnail_url: '/api/v1/prints/20000000-0000-0000-0000-000000000001/thumbnail',
    estimated_duration_seconds: '5400',
    print_duration_seconds: '2700',
    predicted_filament_weight_g: '42',
    actual_filament_weight_g: '20.5',
    actual_filament_cost: '0.62',
    predicted_filament_cost: '1.26',
    cost_currency: 'USD',
    cost_complete: true,
    checked_at: '2026-08-25T00:30:00Z',
  },
}

async function mockDashboard(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/thumbnail')) {
      await route.fulfill({
        contentType: 'image/svg+xml',
        body: thumbnailSvg,
      })
      return
    }
    const json = path.endsWith('/auth/me')
      ? { id: 'admin-id', username: 'admin', display_name: 'Administrator', role: 'administrator', is_active: true, must_change_password: false, record_version: 1 }
      : path.endsWith('/dashboard')
        ? dashboard
        : path.endsWith('/notifications')
          ? []
          : []
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(json) })
  })
}

test('live printer dashboard card is responsive in light and dark profiles', async ({ page }) => {
  await mockDashboard(page)
  await page.goto('/')
  await page.evaluate(() => localStorage.setItem('filament-manager-theme', 'light-navy'))
  await page.reload()
  await expect(page.getByRole('heading', { name: 'IPLT-Max' })).toBeVisible()
  await expect(page.getByText('64%')).toBeVisible()
  await expect(page.getByText('220 °C / 220 °C target')).toBeVisible()
  await expect(page.getByAltText('Preview of functional-part.gcode')).toBeVisible()
  await expect(page.getByText('20.5 g')).toBeVisible()
  await expect(page.getByText('$0.62')).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/dashboard-printer-state-light-v057.png', fullPage: true })

  await page.evaluate(() => localStorage.setItem('filament-manager-theme', 'dark-navy'))
  await page.reload()
  await expect(page.getByRole('heading', { name: 'IPLT-Max' })).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/dashboard-printer-state-dark-v057.png', fullPage: true })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await expect(page.getByRole('region', { name: 'Live printer temperatures' })).toBeVisible()
  await expect(page.getByText('$0.62')).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/dashboard-printer-state-mobile-v057.png', fullPage: true })
})
