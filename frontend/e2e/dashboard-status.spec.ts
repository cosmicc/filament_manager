import { expect, test, type Page } from '@playwright/test'

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
    checked_at: '2026-08-25T00:30:00Z',
  },
}

async function mockDashboard(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
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
  await page.screenshot({ path: '../docs/design/validation/dashboard-printer-state-light-v041.png', fullPage: true })

  await page.evaluate(() => localStorage.setItem('filament-manager-theme', 'dark-navy'))
  await page.reload()
  await expect(page.getByRole('heading', { name: 'IPLT-Max' })).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/dashboard-printer-state-dark-v041.png', fullPage: true })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await expect(page.getByRole('region', { name: 'Live printer temperatures' })).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/dashboard-printer-state-mobile-v041.png', fullPage: true })
})
