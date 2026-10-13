import { expect, test } from '@playwright/test'

for (const width of [1440, 390]) {
  test(`Material type creation and global rename at ${width}px`, async ({ page }) => {
    const errors: string[] = []
    const writes: string[] = []
    let types = ['PLA-CF', 'PETG-CF', 'ASA-CF', 'ASA-GF'].map((name, index) => ({ id: `type-${index}`, name, record_version: 1 }))
    await page.setViewportSize({ width, height: 1000 })
    await page.addInitScript((theme) => localStorage.setItem('filament-manager-theme', theme), width === 390 ? 'light-navy' : 'dark-navy')
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
    await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
      const method = route.request().method()
      if (path === '/auth/me') return route.fulfill({ json: { id: 'admin', username: 'admin', display_name: 'Administrator', role: 'administrator', is_active: true, must_change_password: false } })
      if (path === '/profiles/material-types' && method === 'POST') {
        writes.push(path)
        const item = { id: 'created', name: route.request().postDataJSON().name, record_version: 1 }
        types = [...types, item]
        return route.fulfill({ status: 201, json: item })
      }
      if (path.startsWith('/profiles/material-types/') && method === 'PUT') {
        const payload = route.request().postDataJSON()
        const item = types.find(item => path.endsWith(`/${item.id}`))!
        expect(payload.confirmation_name).toBe(item.name)
        expect(payload.expected_version).toBe(item.record_version)
        writes.push(path)
        types = types.map(value => value === item ? { ...value, name: payload.name, record_version: value.record_version + 1 } : value)
        return route.fulfill({ json: types.find(value => value.id === item.id) })
      }
      if (path === '/profiles/material-types') return route.fulfill({ json: types })
      if (path === '/printers') return route.fulfill({ json: [{ id: 'printer', name: 'Workshop printer', active_nozzle_id: 'nozzle' }] })
      if (path === '/nozzles') return route.fulfill({ json: [{ id: 'nozzle', printer_id: 'printer', nozzle_code: 'N1', diameter_mm: '0.4', material: 'Hardened steel' }] })
      if (method !== 'GET') errors.push(`Unexpected write: ${path}`)
      return route.fulfill({ json: [] })
    })
    await page.goto('/templates')
    await expect(page).toHaveTitle('Filament Manager')
    await expect(page.getByRole('heading', { name: 'Material templates', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Add template', exact: true }).click()
    const editor = page.getByRole('dialog', { name: 'Add material template' })
    await editor.getByLabel('Description', { exact: true }).fill('Keep my template draft')
    const select = editor.getByLabel('Material type', { exact: true })
    await expect(select.locator('option[value="ASA-CF"]')).toHaveCount(1)
    await select.selectOption('ASA-CF')
    await select.selectOption('__filament_manager_new_item__')
    await page.getByRole('dialog', { name: 'New Material Type', exact: true }).getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(select).toHaveValue('ASA-CF')
    await select.selectOption('__filament_manager_new_item__')
    const child = page.getByRole('dialog', { name: 'New Material Type', exact: true })
    await child.getByLabel('Material type name').fill('PA-GF')
    await child.getByRole('button', { name: 'Add material type', exact: true }).click()
    await expect(select).toHaveValue('PA-GF')
    await expect(editor.getByLabel('Description', { exact: true })).toHaveValue('Keep my template draft')
    expect(writes).toEqual(['/profiles/material-types'])
    await editor.getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.getByRole('button', { name: 'Manage material types' }).click()
    const manager = page.getByRole('dialog', { name: 'Manage material types' })
    await manager.getByLabel('Managed material type').selectOption('PA-GF')
    await manager.getByLabel('New name', { exact: true }).fill('PA6-GF')
    await manager.getByLabel('Type PA-GF to confirm').fill('PA-GF')
    const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
    if (evidence) await page.screenshot({ path: `${evidence}/material-types-${width}.png` })
    await manager.getByRole('button', { name: 'Rename material type everywhere' }).click()
    await expect(manager.getByRole('status')).toContainText('renamed to PA6-GF')
    await expect(manager.getByLabel('Managed material type').locator('option[value="PA6-GF"]')).toHaveCount(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect(await page.locator('vite-error-overlay').count()).toBe(0)
    expect(errors).toEqual([])
  })
}
