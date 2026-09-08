import { expect, test, type Page } from '@playwright/test'
import { THEME_OPTIONS } from '../src/context/ThemeContext'
import { thumbnailFixture } from './helpers/thumbnail-fixtures'

const thumbnailSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300"><defs><linearGradient id="background" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#0c2238"/><stop offset="1" stop-color="#17607b"/></linearGradient></defs><rect width="400" height="300" rx="18" fill="url(#background)"/><path d="M200 62 294 114v92l-94 52-94-52v-92z" fill="#d8edf5" stroke="#77c8e4" stroke-width="8"/><path d="m106 114 94 54 94-54M200 168v90" fill="none" stroke="#17607b" stroke-width="8"/><text x="200" y="38" fill="#fff" font-family="sans-serif" font-size="18" text-anchor="middle">G-code preview</text></svg>`

const dashboard = {
  total_spools: 18,
  material_spool_counts: { PLA: 6, 'PLA+': 3, PETG: 4, TPU: 2, ASA: 3 },
  distinct_colors: 9,
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

test('confirmed power-off is neutral rather than a printer error', async ({ page }) => {
  await mockDashboard(page)
  await page.route('**/api/v1/dashboard', route => route.fulfill({ json: {
    ...dashboard, printer_state: { ...dashboard.printer_state, operational_status: 'powered_off',
      klipper_state: 'shutdown', print_state: null, filename: null, progress_percent: null,
      nozzle_temperature_c: null, bed_temperature_c: null, chamber_temperature_c: null,
      thumbnail_url: null, print_job_id: null },
  } }))
  await page.goto('/')
  const status = page.locator('.printer-state-card .status-pill')
  await expect(status).toHaveText('Powered Off')
  await expect(status).toHaveClass(/status-pill--neutral/)
})

async function mockDashboard(page: Page) {
  await page.route('**/runtime-config.js', (route) => route.fulfill({
    contentType: 'application/javascript',
    body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};',
  }))
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

test('a black dashboard preview stays visible without extra polling image requests', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (['error', 'warning'].includes(message.type())) errors.push(message.text()) })
  await mockDashboard(page)
  const png = await thumbnailFixture(page, 'black')
  let thumbnailRequests = 0
  await page.route('**/api/v1/prints/*/thumbnail', (route) => {
    thumbnailRequests++
    return route.fulfill({ contentType: 'image/png', body: png })
  })
  await page.addInitScript(() => localStorage.setItem('filament-manager-theme', 'dark-navy'))
  await page.goto('/')
  await expect(page).toHaveTitle(/Filament Manager/)
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible()
  const preview = page.locator('.printer-current-print__thumbnail')
  await expect(preview).toHaveClass(/adaptive-thumbnail--light/)
  await expect(preview.locator('img')).toHaveCSS('filter', 'brightness(1) contrast(1)')
  await page.screenshot({ path: testInfo.outputPath('dashboard-black-preview.png'), fullPage: true })
  const before = thumbnailRequests
  await page.getByRole('button', { name: 'Collapse navigation' }).click()
  await expect(preview.locator('img')).toBeVisible()
  await page.waitForTimeout(10_500)
  expect(thumbnailRequests).toBe(before)
  await expect(page.locator('vite-error-overlay')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('all twelve approved accents match their previews and retain readable contrast', async ({ page }) => {
  await mockDashboard(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'IPLT-Max' })).toBeVisible()
  const luminance = (hex: string) => {
    const raw = hex.replace('#', '')
    const expanded = raw.length === 3 ? [...raw].map((part) => part + part).join('') : raw
    const channels = expanded.match(/.{2}/g)!.map((part) => {
      const value = parseInt(part, 16) / 255
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
    })
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
  }
  for (const theme of THEME_OPTIONS) {
    expect(theme.swatches).toHaveLength(4)
    const tokens = await page.evaluate((id) => {
      document.documentElement.dataset.theme = id
      const style = getComputedStyle(document.documentElement)
      return Object.fromEntries(['--accent', '--surface', '--surface-muted', '--surface-page', '--warning'].map((key) => [key, style.getPropertyValue(key).trim()]))
    }, theme.id)
    expect(tokens['--accent'].toUpperCase()).toBe(theme.swatches[3])
    expect(tokens['--accent']).not.toBe(tokens['--warning'])
    for (const surface of ['--surface', '--surface-muted', '--surface-page']) {
      const colors = [luminance(tokens['--accent']), luminance(tokens[surface])]
      expect((Math.max(...colors) + 0.05) / (Math.min(...colors) + 0.05), theme.id).toBeGreaterThanOrEqual(4.5)
    }
  }
})

test('live printer dashboard card is responsive in light and dark profiles', async ({ page }, testInfo) => {
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
  await expect(page.getByRole('heading', { name: 'Quick actions' })).toHaveCount(0)
  await expect(page.locator('.dashboard-page .page-header__actions a')).toHaveCount(6)
  await expect(page.locator('.dashboard-metric-grid .metric-card')).toHaveCount(9)
  await page.screenshot({ path: testInfo.outputPath('dashboard-light-v072.png'), fullPage: true })

  await page.evaluate(() => localStorage.setItem('filament-manager-theme', 'dark-navy'))
  await page.reload()
  await expect(page.getByRole('heading', { name: 'IPLT-Max' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('dashboard-dark-v072.png'), fullPage: true })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await expect(page.getByRole('region', { name: 'Live printer temperatures' })).toBeVisible()
  await expect(page.getByText('$0.62')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  for (const button of await page.locator('.dashboard-page .page-header__actions a').all()) {
    await expect(button).toBeVisible()
    expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  }
  expect((await page.locator('.dashboard-metric-grid .metric-card').first().boundingBox())!.height).toBeLessThan(96)
  await page.screenshot({ path: testInfo.outputPath('dashboard-mobile-v072.png'), fullPage: true })
})

test('printer carousel scopes actions and remains usable on mobile', async ({ page }, testInfo) => {
  await mockDashboard(page)
  const contexts = ['First printer', 'Second printer'].map((name, index) => ({
    printer_id: `printer-${index}`, active_spools: [], active_plate: null, active_plate_surface: null,
    printer_state: { ...dashboard.printer_state, printer_name: name, thumbnail_url: null },
  }))
  await page.route('**/api/v1/dashboard', route => route.fulfill({ json: { ...dashboard, printer_contexts: contexts } }))
  const queued: string[] = []
  await page.route('**/api/v1/printers/*/sync-cura', route => { queued.push(new URL(route.request().url()).pathname); return route.fulfill({ json: { queued: 1 } }) })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'First printer', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Next printer', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Second printer', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Load spool', exact: true })).toHaveAttribute('href', '/spools?action=load&printer_id=printer-1')
  await page.getByRole('button', { name: 'Sync to Cura', exact: true }).click()
  await expect.poll(() => queued).toEqual(['/api/v1/printers/printer-1/sync-cura'])
  await page.getByRole('button', { name: 'Next printer', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'First printer', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Second printer', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Second printer', exact: true })).toBeVisible()
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    for (const name of ['Previous printer', 'Next printer', 'Sync to Cura']) {
      const button = page.getByRole('button', { name, exact: true })
      await expect(button).toBeVisible()
      if (width === 390) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    }
    await page.screenshot({ path: testInfo.outputPath(`carousel-${width}.png`), fullPage: true })
  }
})
