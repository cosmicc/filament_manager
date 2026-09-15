import { expect, test } from '@playwright/test'

for (const theme of ['light-navy', 'dark-navy']) {
  test(`dashboard status colors and workstation sync in ${theme}`, async ({ page }) => {
    const errors: string[] = []
    const requests: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('console', message => { if (['error', 'warning'].includes(message.type())) errors.push(message.text()) })
    await page.addInitScript(value => localStorage.setItem('filament-manager-theme', value), theme)
    const states = ['idle', 'printing', 'paused', 'powered_off', 'error', 'finished', 'cancelled', 'starting']
    const spool = { id: 'spool-one', spool_code: 'P1', filament_product_id: 'filament-one', vendor_name: 'Workshop', material_type: 'PLA', color_name: 'Blue', color_hexes: ['2457A6'], color_mode: 'solid', remaining_percent: '75', remaining_mass_effective_g: '750', active_extruder: 'extruder' }
    const plate = { id: 'plate-one', plate_code: 'P1', display_name: 'Smooth PEI', image_url: null }
    const contexts = states.map((state, index) => ({
      printer_id: `printer-${index}`, active_spools: [spool], active_plate: plate, active_plate_surface: null,
      printer_state: { printer_name: `Printer ${index + 1}`, connection_status: 'connected', operational_status: state, klipper_state: ['powered_off', 'error'].includes(state) ? 'shutdown' : 'ready', print_state: ['idle', 'powered_off', 'error'].includes(state) ? null : state, nozzle_temperature_c: state === 'powered_off' ? null : '24', bed_temperature_c: state === 'powered_off' ? null : '23', checked_at: '2026-09-14T12:00:00Z' },
    }))
    const agent = { id: 'agent-one', display_name: 'Slicing computer', enabled: true, cura_management_enabled: true, cura_installations: [{ machines: [{ display_name: 'Completely unrelated machine name' }] }] }
    let agents = [agent]
    await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
      requests.push(`${route.request().method()} ${path}`)
      let json: unknown = []
      if (path === '/auth/me') json = { id: 'admin', username: 'admin', role: 'administrator', is_active: true, must_change_password: false }
      else if (path === '/dashboard') json = { total_spools: 1, material_spool_counts: { PLA: 1 }, distinct_colors: 1, needs_weighing: 0, low_spools: 0, empty_spools: 0, printer_contexts: contexts, printer_state: contexts[0].printer_state, active_spool: spool, active_plate: plate, active_plate_surface: null }
      else if (path === '/workstation-agents') json = agents
      else if (path.endsWith('/sync')) json = [{ id: 'deployment-one', agent_id: path.split('/')[2], status: 'pending' }]
      await route.fulfill({ json })
    })
    await page.goto('/')
    await expect(page).toHaveTitle('Filament Manager')
    await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Calibrate', exact: true })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Build plate', exact: true })).toHaveCount(0)
    expect(requests.some(path => path.includes('workstation'))).toBe(false)
    const card = page.locator('.printer-state-card')
    const colors: Record<string, string> = { printing: '--success', paused: '--paused', powered_off: '--warning', error: '--danger' }
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 })
      for (const state of states) {
        await expect(card).toHaveClass(new RegExp(`printer-state-card--${state}\\b`))
        const result = await card.evaluate((node, token) => {
          const style = getComputedStyle(node)
          const root = getComputedStyle(document.documentElement)
          return { stateColor: style.getPropertyValue('--printer-state-color').trim(), expected: token ? root.getPropertyValue(token).trim() : '', stripe: getComputedStyle(node, '::before').backgroundColor }
        }, colors[state])
        expect(result.stateColor).toBe(result.expected)
        if (!colors[state]) expect(result.stripe).toBe('rgba(0, 0, 0, 0)')
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
        const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
        if (evidence && ['printing', 'paused', 'powered_off', 'error'].includes(state)) await page.screenshot({ path: `${evidence}/dashboard-${state}-${theme}-${width}-v086.png`, fullPage: true })
        await page.getByRole('button', { name: 'Next printer', exact: true }).click()
      }
      for (const selector of ['.active-spool-card--active', '.plate-card']) {
        expect(await page.locator(selector).evaluate(node => {
          const reference = document.createElement('article')
          reference.className = 'card'
          document.body.append(reference)
          const actual = getComputedStyle(node)
          const expected = getComputedStyle(reference)
          const neutral = actual.backgroundColor === expected.backgroundColor && actual.borderTopColor === expected.borderTopColor
          reference.remove()
          return neutral
        })).toBe(true)
      }
      await expect(page.locator('.active-spool > .filament-swatch')).toHaveCSS('width', '64px')
    }
    await page.getByRole('button', { name: 'Sync to Cura', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('App settings queued for Slicing computer')
    expect(requests).toContain('POST /workstation-agents/agent-one/sync')
    expect(requests.some(path => path.includes('/sync-cura'))).toBe(false)
    agents = [agent, { ...agent, id: 'agent-two', display_name: 'Second computer' }]
    await page.getByRole('button', { name: 'Sync to Cura', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Sync to Cura', exact: true })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
    expect(requests.filter(path => path.startsWith('POST'))).toHaveLength(1)
    await page.getByRole('button', { name: 'Sync to Cura', exact: true }).click()
    await dialog.getByRole('button', { name: 'Sync to Second computer', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('App settings queued for Second computer')
    expect(requests).toContain('POST /workstation-agents/agent-two/sync')
    await expect(page.locator('vite-error-overlay')).toHaveCount(0)
    expect(errors).toEqual([])
  })
}
