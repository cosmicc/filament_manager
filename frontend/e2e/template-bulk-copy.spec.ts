import { expect, test } from '@playwright/test'

for (const width of [1440, 390]) {
  test(`fill unset template values and save or cancel at ${width}px`, async ({ page }) => {
    const errors: string[] = []
    const writes: Record<string, unknown>[] = []
    const source = {
      id: 'source', name: 'Template ASA', material_type: 'ASA', printer_id: 'printer', nozzle_id: 'nozzle',
      nozzle_diameter_mm: '0.4', filament_diameter_mm: '1.75', active: true, record_version: 1,
      revisions: [{ id: 'revision', version: 1, settings: {
        extruder_temp_c: '250', bed_temp_c: '95', initial_bed_temp_c: '100', chamber_temp_c: '45', flow_percent: '100',
        filament_density_g_cm3: '1.07', drying_temp_c: '80', drying_time_hours: '6-8', moisture_sensitivity: 'high',
        shore_hardness: { scale: 'D', value: '75' }, cura_extensions: {},
      } }],
    }
    await page.setViewportSize({ width, height: 1000 })
    await page.addInitScript(theme => localStorage.setItem('filament-manager-theme', theme), width === 390 ? 'light-navy' : 'dark-navy')
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
      if (path === '/auth/me') return route.fulfill({ json: { id: 'admin', username: 'admin', role: 'administrator', is_active: true, must_change_password: false } })
      if (path === '/profiles/templates' && route.request().method() === 'POST') {
        writes.push(route.request().postDataJSON())
        return route.fulfill({ status: 201, json: source })
      }
      if (path === '/profiles/templates') return route.fulfill({ json: [source] })
      if (path === '/profiles/material-types') return route.fulfill({ json: [{ id: 'asa', name: 'ASA', record_version: 1 }, { id: 'cf', name: 'ASA-CF', record_version: 1 }] })
      if (path === '/printers') return route.fulfill({ json: [{ id: 'printer', name: 'Workshop printer', active_nozzle_id: 'nozzle' }] })
      if (path === '/nozzles') return route.fulfill({ json: [{ id: 'nozzle', printer_id: 'printer', nozzle_code: 'N1', diameter_mm: '0.4', material: 'Hardened steel' }] })
      return route.fulfill({ json: [] })
    })
    await page.goto('/templates')
    await expect(page).toHaveTitle('Filament Manager')
    await page.getByRole('button', { name: 'Add template', exact: true }).click()
    const editor = page.getByRole('dialog', { name: 'Add material template' })
    await editor.getByLabel('Material type', { exact: true }).selectOption('ASA-CF')
    await editor.getByLabel('Printing temperature (°C)', { exact: true }).fill('260')
    await page.getByRole('combobox', { name: 'Source template', exact: true }).selectOption('source')
    await editor.getByRole('button', { name: 'Fill unset values', exact: true }).click()
    await expect(editor.getByLabel('Printing temperature (°C)', { exact: true })).toHaveValue('260')
    await expect(editor.getByLabel('Build volume temperature (°C)', { exact: true })).toHaveValue('45')
    await expect(editor.getByLabel('Shore hardness value')).toHaveValue('75')
    await expect(editor.getByLabel('Shore hardness scale')).toHaveValue('D')
    await expect(editor.getByLabel('Material type', { exact: true })).toHaveValue('ASA-CF')
    expect(writes).toHaveLength(0)
    await editor.getByRole('button', { name: 'Fill unset values', exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: `/tmp/fm-bulk-copy-${width}.png` })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await editor.getByRole('button', { name: 'Cancel', exact: true }).click()
    expect(writes).toHaveLength(0)
    await page.getByRole('button', { name: 'Add template', exact: true }).click()
    await expect(editor.getByLabel('Build volume temperature (°C)', { exact: true })).toHaveValue('')
    await editor.getByLabel('Material type', { exact: true }).selectOption('ASA-CF')
    await page.getByRole('combobox', { name: 'Source template', exact: true }).selectOption('source')
    await editor.getByRole('button', { name: 'Fill unset values', exact: true }).click()
    await editor.getByRole('button', { name: 'Save template', exact: true }).click()
    await expect(editor).toHaveCount(0)
    expect(writes).toHaveLength(1)
    expect(writes[0].settings).toMatchObject({ chamber_temp_c: '45', shore_hardness: { scale: 'D', value: '75' }, drying_time_hours: '6-8' })
    expect(errors).toEqual([])
  })
}
