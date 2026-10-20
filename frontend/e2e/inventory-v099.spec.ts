import { expect, test } from '@playwright/test'

for (const width of [1440, 390]) {
  test(`uppercase manufacturer rename and automatic named multicolor at ${width}px`, async ({ page }) => {
    const errors: string[] = []
    const writes: Record<string, unknown>[] = []
    const manufacturers = [{ id: 'maker', name: 'MAKER', record_version: 1 }, { id: 'unknown', name: 'UNKNOWN', record_version: 1 }]
    const colors = [['Red', 'FF0000'], ['White', 'FFFFFF'], ['Blue', '0000FF']].map(([name, color_hex]) => ({ name, color_hex, color_hexes: [color_hex], normalized_name: name.toLowerCase(), color_mode: 'solid' }))
    await page.setViewportSize({ width, height: 1000 })
    await page.addInitScript(theme => localStorage.setItem('filament-manager-theme', theme), width === 390 ? 'light-navy' : 'dark-navy')
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
      if (path === '/auth/me') return route.fulfill({ json: { id: 'admin', username: 'admin', role: 'administrator', is_active: true, must_change_password: false } })
      if (path === '/vendors/maker') {
        const body = route.request().postDataJSON(); writes.push(body)
        expect(body).toEqual({ name: 'NEW MAKER', confirm_name: 'MAKER', expected_version: 1 })
        manufacturers[0] = { id: 'maker', name: body.name, record_version: 2 }
        return route.fulfill({ json: manufacturers[0] })
      }
      if (path === '/vendors') return route.fulfill({ json: manufacturers })
      if (path === '/filament-colors') return route.fulfill({ json: colors })
      if (path === '/profiles/templates') return route.fulfill({ json: [{ id: 'template', name: 'Template PLA', material_type: 'PLA', active: true, nozzle_diameter_mm: '0.4', revisions: [{ id: 'revision', version: 1, settings: { filament_density_g_cm3: '1.24' } }] }] })
      return route.fulfill({ json: [] })
    })
    await page.goto('/filaments')
    await expect(page).toHaveTitle('Filament Manager')
    await expect(page.getByRole('heading', { name: 'Filaments', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Manage manufacturers' }).click()
    const manager = page.getByRole('dialog', { name: 'Manage manufacturers' })
    await manager.getByLabel('Manufacturer', { exact: true }).selectOption('maker')
    await manager.getByLabel('New manufacturer name').fill('new maker')
    await expect(manager.getByLabel('New manufacturer name')).toHaveValue('NEW MAKER')
    await manager.getByLabel('Type MAKER to confirm').fill('MAKER')
    await manager.getByRole('button', { name: 'Rename manufacturer' }).click()
    await expect(manager.getByLabel('Manufacturer', { exact: true })).toHaveValue('')
    await manager.getByLabel('Manufacturer', { exact: true }).selectOption('maker')
    await expect(manager.getByText('Type NEW MAKER to confirm')).toBeVisible()
    await page.screenshot({ path: `/tmp/fm099-manufacturers-${width}.png` })
    await manager.getByRole('button', { name: 'Close', exact: true }).click()
    await page.getByRole('button', { name: 'Add filament', exact: true }).click()
    const editor = page.getByRole('dialog', { name: 'Add a filament' })
    await editor.getByLabel('Color name', { exact: true }).selectOption('Red')
    await editor.getByLabel('Number of colors').selectOption('2')
    await expect(editor.getByLabel('Color name', { exact: true })).toBeDisabled()
    await expect(editor.getByLabel('Color name', { exact: true })).toHaveValue('Multicolor')
    await editor.getByLabel('Color 2', { exact: true }).selectOption('White')
    await editor.getByLabel('Number of colors').selectOption('3')
    await editor.getByLabel('Color 3', { exact: true }).selectOption('Blue')
    await expect(editor.getByLabel('Color 1', { exact: true })).toHaveValue('Red')
    await page.screenshot({ path: `/tmp/fm099-colors-${width}.png` })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await editor.getByLabel('Number of colors').selectOption('1')
    await expect(editor.getByLabel('Color name', { exact: true })).toBeEnabled()
    await editor.getByLabel('Color name', { exact: true }).selectOption('Blue')
    await expect(editor.getByLabel('Screen color sample')).toHaveValue('#0000ff')
    expect(writes).toHaveLength(1)
    expect(errors).toEqual([])
  })
}
