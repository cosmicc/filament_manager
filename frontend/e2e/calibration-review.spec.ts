import { expect, test } from '@playwright/test'

for (const [theme, width] of [['dark-navy', 1440], ['light-navy', 390]] as const) {
  test(`calibration review saves explicitly to the template in ${theme}`, async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => {
      // The deliberate conflict below emits Chromium's expected HTTP error log.
      const expectedConflict = message.text().includes('409 (Conflict)')
        || (message.text().startsWith('[Filament Manager API] Request rejected') && message.text().includes('status: 409, code: record_version_conflict'))
      if (['warning', 'error'].includes(message.type()) && !expectedConflict) errors.push(message.text())
    })
    await page.setViewportSize({ width, height: 950 })
    await page.addInitScript(value => localStorage.setItem('filament-manager-theme', value), theme)
    let applied = false
    let reject = true
    const writes: unknown[] = []
    await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
      let json: unknown = []
      if (path === '/auth/me') json = { id: 'admin', username: 'admin', role: 'administrator', is_active: true, must_change_password: false }
      else if (path === '/calibrations') json = [{ id: 'calibration-one', filament_product_id: 'filament-one', printer_id: 'printer-one', nozzle_diameter_mm: '0.4', build_plate_surface_id: null, record_version: applied ? 2 : 1, status: applied ? 'published' : 'ready_to_publish', steps: [{ id: 'step-one', step_order: 1, step_key: 'temperature', name: 'Temperature Tower', status: 'completed', required: true, result: { extruder_temp_c: '220', bed_temp_c: '60' }, inputs: {}, record_version: 1 }] }]
      else if (path === '/filaments') json = [{ id: 'filament-one', material_type: 'PLA', color_name: 'Blue', vendor_name: 'Workshop' }]
      else if (path === '/printers') json = [{ id: 'printer-one', name: 'Workshop printer' }]
      else if (path.endsWith('/suggestions')) json = { template_id: 'template-one', template_name: 'Template PLA', suggestions: { extruder_temp_c: '220', flow_percent: '97.5000', 'cura_extensions.xy_offset': '-0.075', 'cura_extensions.hole_xy_offset': '0.2000', preferred_build_plate_surface_id: 'legacy-side-id' } }
      else if (path.endsWith('/apply-template-settings')) {
        writes.push(route.request().postDataJSON())
        if (reject) return route.fulfill({ status: 409, json: { code: 'record_version_conflict', message: 'Calibration changed; reload', correlation_id: 'test-reference' } })
        applied = true
        json = { status: 'published' }
      }
      else if (path.endsWith('/apply-profile-settings')) throw new Error('Template save must not call the filament-only endpoint')
      await route.fulfill({ json })
    })
    await page.goto('/calibration')
    await expect(page).toHaveTitle('Filament Manager')
    await expect(page.getByRole('heading', { name: 'Filament Calibration', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Review suggested settings', exact: true }).click()
    const modal = page.getByRole('dialog', { name: 'Suggested Cura settings', exact: true })
    await expect(modal.getByText('Horizontal Expansion', { exact: true })).toBeVisible()
    await expect(modal.getByText('Hole Horizontal Expansion', { exact: true })).toBeVisible()
    await expect(modal.getByText('-0.08 mm', { exact: true })).toBeVisible()
    await expect(modal.getByText('0.2 mm', { exact: true })).toBeVisible()
    await expect(modal.getByText(/Preferred Build Plate|legacy-side-id|Xy Offset/)).toHaveCount(0)
    const update = modal.getByRole('button', { name: 'Update linked template', exact: true })
    await expect(update).toHaveClass(/button--primary/)
    await expect(modal.getByRole('button', { name: 'Save to filament only', exact: true })).not.toHaveClass(/button--primary/)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
    if (evidence) await modal.screenshot({ path: `${evidence}/calibration-review-${theme}-v087.png`, animations: 'disabled' })
    page.once('dialog', dialog => dialog.dismiss())
    await update.click()
    expect(writes).toEqual([])
    page.on('dialog', dialog => dialog.type() === 'prompt' ? dialog.accept('Template PLA') : dialog.accept())
    await update.click()
    await expect(modal.getByRole('alert')).toContainText('Calibration changed; reload')
    await expect(page.getByRole('status')).toHaveCount(0)
    reject = false
    await update.click()
    await expect(modal).toHaveCount(0)
    await expect(page.getByRole('status')).toContainText('Template PLA was updated')
    expect(writes).toEqual([{ expected_version: 1, confirm_template_name: 'Template PLA' }, { expected_version: 1, confirm_template_name: 'Template PLA' }])
    await expect(page.locator('vite-error-overlay')).toHaveCount(0)
    expect(errors).toEqual([])
  })
}
