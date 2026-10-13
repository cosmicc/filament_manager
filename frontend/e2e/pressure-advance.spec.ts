import { expect, test } from '@playwright/test'

for (const width of [1440, 390]) {
  test(`Pressure Advance guidance and exact height calculation at ${width}px`, async ({ page }) => {
    const errors: string[] = []
    const writes: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    await page.setViewportSize({ width, height: 950 })
    await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
      if (route.request().method() !== 'GET') writes.push(path)
      let json: unknown = []
      if (path === '/auth/me') json = { id: 'admin', username: 'admin', role: 'administrator', is_active: true, must_change_password: false }
      else if (path === '/calibrations') json = [{ id: 'calibration-one', filament_product_id: 'filament-one', printer_id: 'printer-one', nozzle_diameter_mm: '0.4', build_plate_surface_id: null, record_version: 1, status: 'in_progress', steps: [{ id: 'step-one', step_order: 3, step_key: 'pressure_advance', name: 'Pressure Advance Square Tower', status: 'in_progress', required: true, result: {}, inputs: {}, record_version: 1 }] }]
      else if (path === '/filaments') json = [{ id: 'filament-one', material_type: 'PLA', color_name: 'Blue', vendor_name: 'Workshop' }]
      else if (path === '/printers') json = [{ id: 'printer-one', name: 'Workshop printer' }]
      await route.fulfill({ json })
    })
    await page.goto('/calibration')
    await expect(page).toHaveTitle('Filament Manager')
    await expect(page.getByText('Run the Klipper Prep PA macro before the Pressure Advance test print.')).toBeVisible()
    const height = page.getByRole('spinbutton', { name: 'Good height (mm)' })
    await height.fill('12.25')
    await expect(page.getByText('PA = 0.245', { exact: true })).toBeVisible()
    const result = page.getByRole('spinbutton', { name: 'Pressure advance factor' })
    await result.fill('0.245')
    expect(await result.evaluate((element: HTMLInputElement) => element.validity.valid)).toBe(true)
    await height.fill('101')
    await expect(height).toHaveAttribute('aria-invalid', 'true')
    expect(await result.evaluate((element: HTMLInputElement) => element.form?.checkValidity())).toBe(true)
    await height.fill('12.25')
    await height.scrollIntoViewIfNeeded()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
    if (evidence) await page.screenshot({ path: `${evidence}/pressure-advance-${width}-v094.png` })
    expect(writes).toEqual([])
    expect(errors).toEqual([])
  })
}
