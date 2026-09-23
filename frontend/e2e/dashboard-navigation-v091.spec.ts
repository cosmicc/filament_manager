import { expect, test } from '@playwright/test'

for (const width of [1280, 390]) {
  test(`inventory shortcuts and power-on at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const errors: string[] = []
    const requests: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    const state = { printer_name: 'Workshop printer', connection_status: 'connected', operational_status: 'powered_off', klipper_state: 'shutdown' }
    const plate = { id: 'plate-one', plate_code: 'P1', display_name: 'Smooth PEI', surfaces: [], record_version: 1, status: 'available', condition: 'good' }
    await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url())
      const path = url.pathname.replace('/api/v1', '')
      requests.push(`${route.request().method()} ${path}${url.search}`)
      let json: unknown = []
      if (path === '/auth/me') json = { id: 'admin', username: 'admin', role: 'administrator', is_active: true, must_change_password: false }
      else if (path === '/dashboard') json = { total_spools: 2, material_spool_counts: { ASA: 2 }, distinct_colors: 1, color_spool_counts: { blue: 2 }, needs_weighing: 1, low_spools: 1, empty_spools: 0, printer_state: state, printer_contexts: [{ printer_id: 'printer-one', printer_state: state, active_spools: [], active_plate: plate }] }
      else if (path === '/printers/printer-one/power-on') json = { status: 'on' }
      else if (path === '/printers') json = [{ id: 'printer-one', name: 'Workshop printer' }]
      else if (path === '/build-plates') json = [plate]
      else if (path === '/spools') json = { items: [], total: 0, limit: 200, offset: 0 }
      else if (path === '/notifications') json = []
      await route.fulfill({ json })
    })
    await page.goto('/')
    await page.getByRole('button', { name: 'Power on', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Power on accepted' })).toBeDisabled()
    expect(requests.filter(value => value.startsWith('POST'))).toEqual(['POST /printers/printer-one/power-on'])
    await page.screenshot({ path: `/tmp/filament-091-dashboard-${width}.png`, fullPage: true })
    await page.getByRole('link', { name: /ASA/ }).click()
    await expect(page).toHaveURL(/\/spools\?view=list&material=asa/)
    await expect.poll(() => requests.some(value => value.includes('/spools?') && value.includes('material=asa'))).toBe(true)
    await page.goto('/')
    await page.getByRole('button', { name: /Colors/ }).click()
    await page.getByRole('link', { name: /Blue/ }).click()
    await expect.poll(() => requests.some(value => value.includes('/spools?') && value.includes('color=blue'))).toBe(true)
    await page.goto('/')
    await page.getByRole('link', { name: 'Open build plate Smooth PEI details' }).click()
    await expect(page.getByRole('dialog', { name: 'P1 details', exact: true })).toBeVisible()
    expect(errors).toEqual([])
  })
}
