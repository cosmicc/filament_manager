import { expect, test } from '@playwright/test'

test('printer setup submits write-only credentials and preserves capability fields', async ({ page }) => {
  const submitted: Record<string, unknown>[] = []
  let printers: Record<string, unknown>[] = []
  await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'admin-id', username: 'admin', display_name: 'Administrator', role: 'administrator', is_active: true, must_change_password: false, record_version: 1 } })
    if (path.endsWith('/printers') && route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      submitted.push(body)
      printers = [{ id: 'printer-1', printer_code: 'printer-1', name: body.name, extruder_count: body.extruder_count, build_volume: {}, record_version: 1, active_spools: [] }]
      return route.fulfill({ status: 201, json: printers[0] })
    }
    if (path.endsWith('/printers')) return route.fulfill({ json: printers })
    return route.fulfill({ json: [] })
  })
  await page.goto('/printers')
  await page.getByRole('button', { name: 'Add 3D printer', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add 3D printer', exact: true })
  await dialog.getByLabel('Printer name').fill('Workshop printer')
  await dialog.getByLabel('Independent hotends').fill('2')
  await dialog.getByLabel('Moonraker URL').fill('http://printer.example.test:7125')
  await dialog.getByLabel('Moonraker API key').fill('test-only-printer-key')
  await dialog.getByRole('button', { name: 'Save printer', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(submitted).toEqual([{ name: 'Workshop printer', extruder_count: 2, base_url: 'http://printer.example.test:7125', enabled: true, api_key: 'test-only-printer-key' }])
  await expect(page.getByRole('heading', { name: 'Workshop printer', exact: true })).toBeVisible()
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain('test-only-printer-key')
})
