import { expect, test, type Page } from '@playwright/test'

async function captureEvidence(page: Page, name: string, fullPage = false): Promise<void> {
  const directory = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
  if (directory) await page.screenshot({ path: `${directory}/${name}.png`, fullPage })
}

const user = {
  id: 'administrator-id',
  username: 'admin',
  display_name: 'Administrator',
  role: 'administrator',
  is_active: true,
  must_change_password: false,
  record_version: 1,
}
const checkedAt = '2026-08-14T12:00:00Z'

test.beforeEach(async ({ page }) => {
  await page.route('**/runtime-config.js', (route) => route.fulfill({
    contentType: 'application/javascript',
    body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};',
  }))
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/notifications**', (route) => route.fulfill({ json: [] }))
})

test('diagnostics consolidates operational status and recovery controls', async ({ page }) => {
  await page.route(/\/api\/v1\/diagnostics\/log\.txt\?error_days=(?:1|7|30)$/, (route) => route.fulfill({
    status: 200,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Content-Disposition': 'attachment; filename="filament-manager-diagnostics-20260814T120000Z.txt"',
    },
    body: 'Filament Manager diagnostics\nGenerated: 2026-08-14T12:00:00Z\n',
  }))
  await page.route('**/api/v1/diagnostics/version', (route) => route.fulfill({ json: {
    running_version: '0.7.0', latest_version: '0.7.0', status: 'current',
    release_url: 'https://github.com/cosmicc/filament_manager/releases/tag/v0.7.0',
    detail: 'This installation matches the newest published GitHub release.',
  } }))
  await page.route(/\/api\/v1\/diagnostics\?error_days=(?:1|7|30)$/, (route) => route.fulfill({ json: {
    checked_at: checkedAt,
    checks: [
      { key: 'database', label: 'Canonical database', category: 'connection', status: 'healthy', detail: 'Connected at the expected schema revision.', checked_at: checkedAt },
      { key: 'cura', label: 'Cura synchronization', category: 'synchronization', status: 'warning', detail: 'One paired workstation has not reported recently.', checked_at: checkedAt },
      { key: 'worker', label: 'Projection worker', category: 'worker', status: 'healthy', detail: 'Heartbeat received recently.', checked_at: checkedAt },
      { key: 'spools', label: 'Active spool state', category: 'operational', status: 'healthy', detail: 'Physical and projected state agree.', checked_at: checkedAt },
    ],
    queue_counts: { pending: 2, failed: 0, dead: 0 },
    job_type_counts: { 'spoolman.spool.upsert': 2 },
    error_log: [{
      source: 'Cura backup request', severity: 'error', summary: 'RuntimeError',
      detail: 'The earlier named backup did not complete safely.', occurred_at: checkedAt,
      correlation_id: null, current: false,
    }],
  } }))
  await page.route('**/api/v1/diagnostics/validation-runs', (route) => route.fulfill({ json: [{
    id: 'validation-id', run_type: 'recovery_validation', status: 'completed', requested_by: 'administrator-id',
    started_at: checkedAt, completed_at: checkedAt,
    results: {
      summary: { healthy: 1, warning: 1, error: 1, disabled: 0 },
      checks: [
        { key: 'recorded-recovery', label: 'Recorded recovery check', category: 'recovery', status: 'healthy', detail: 'Healthy when validation ran.', checked_at: checkedAt },
        { key: 'recorded-cura', label: 'Recorded Cura error', category: 'synchronization', status: 'error', detail: 'Unavailable when validation ran.', checked_at: checkedAt },
        { key: 'recorded-queue', label: 'Recorded queue warning', category: 'worker', status: 'warning', detail: 'Retrying when validation ran.', checked_at: checkedAt },
      ],
    },
  }] }))
  await page.route('**/api/v1/jobs?limit=100', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/diagnostics/database-backups', (route) => route.fulfill({ json: {
    policy: { enabled: true, interval_hours: 24, retention_count: 10, record_version: 2 },
    status: { status: 'error', checked_at: checkedAt, last_success_at: null, consecutive_failures: 1, next_retry_at: '2026-08-14T12:15:00Z', last_error_message: 'The private application data volume is not writable by Filament Manager.' },
    pending_restore: null,
    archives: [],
  } }))

  await page.goto('/diagnostics')

  await expect(page.getByRole('heading', { name: 'Diagnostics' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Filament Manager v0.7.0' })).toBeVisible()
  await expect(page.getByText('Latest: v0.7.0')).toBeVisible()
  await expect(page.getByText('v0.7.0', { exact: true }).first()).toBeVisible()
  await expect(page.locator('.sidebar').getByRole('button', { name: 'Logout' })).toHaveCount(0)
  const navigationLinks = page.getByRole('navigation', { name: 'Main navigation' }).locator('a')
  const navigationPaths = await navigationLinks.evaluateAll((links) => links.map((link) => link.getAttribute('href')))
  expect(navigationPaths.indexOf('/prints')).toBe(navigationPaths.indexOf('/printers') + 1)
  await expect(page.getByRole('button', { name: 'Collapse navigation' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Connections' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Synchronizations' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Workers and queues' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recent errors' })).toBeVisible()
  await expect(page.getByLabel('Recent error period')).toHaveValue('1')
  const sevenDayRequest = page.waitForRequest((request) => request.url().endsWith('/api/v1/diagnostics?error_days=7'))
  await page.getByLabel('Recent error period').selectOption('7')
  await sevenDayRequest
  await expect(page.getByText('Recorded Cura error')).toBeVisible()
  await expect(page.getByText('Recorded queue warning')).toBeVisible()
  await expect(page.getByText('History', { exact: true })).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download log' }).click()
  await expect((await downloadPromise).suggestedFilename()).toBe('filament-manager-diagnostics-20260814T120000Z.txt')
  await expect(page.getByRole('button', { name: 'Run validation' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Rebuild projections/ })).toBeVisible()
  await expect(page.getByText('Automatic backup schedule')).toBeVisible()
  await expect(page.getByLabel('Automatic backup interval in hours')).toHaveValue('24')
  await expect(page.getByLabel('Automatic backups retained')).toHaveValue('10')
  await expect(page.getByText(/data volume is not writable/)).toBeVisible()
  await captureEvidence(page, 'diagnostics-v067', true)
  await page.getByRole('button', { name: 'Collapse navigation' }).click()
  await expect(page.getByRole('button', { name: 'Expand navigation' }).locator('.lucide-chevron-right')).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('heading', { name: 'Database backups', exact: true }).scrollIntoViewIfNeeded()
  await expect(page.getByLabel('Automatic backup interval in hours')).toBeVisible()
  await expect(page.getByLabel('Automatic backups retained')).toBeVisible()
  await captureEvidence(page, 'diagnostics-backups-mobile-v067', true)
})

test('theme control lives in Settings instead of the navigation', async ({ page }) => {
  await page.route('**/api/v1/settings/operational', (route) => route.fulfill({ json: {
    gcode_inspection_policy: 'warn', record_version: 1,
  } }))
  await page.route('**/api/v1/auth/users', (route) => route.fulfill({ json: [user] }))
  await page.route('**/api/v1/devices', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/imports/workbook?limit=10', (route) => route.fulfill({ json: [] }))

  await page.goto('/settings')

  await expect(page.getByRole('heading', { name: 'Color profile' })).toBeVisible()
  await expect(page.locator('.theme-profile')).toHaveCount(12)
  await expect(page.locator('.theme-profile').filter({ hasText: 'Workshop Navy' }).first()).toBeVisible()
  await expect(page.locator('.theme-profile').filter({ hasText: 'Plum Neon' })).toBeVisible()
  await expect(page.locator('.theme-profile').filter({ hasText: 'Deep Ocean' })).toBeVisible()
  await expect(page.locator('.theme-profile').filter({ hasText: 'Carbon Lime' })).toBeVisible()
  await expect(page.locator('.theme-profile').filter({ hasText: 'Ember Red' })).toBeVisible()
  await expect(page.locator('.theme-profile').filter({ hasText: 'Arctic Slate' })).toBeVisible()
  await expect(page.locator('.sidebar').getByRole('button', { name: /theme/i })).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.locator('.app-shell')).not.toHaveClass(/app-shell--collapsed/)
  await expect.poll(() => page.locator('.sidebar').evaluate((element) => getComputedStyle(element).width)).toBe('310px')
  await expect(page.locator('.sidebar').getByText('v0.7.0', { exact: true })).toBeVisible()
  await expect(page.locator('.sidebar').getByText('Integrations', { exact: true })).toHaveCount(0)
  await expect(page.locator('.sidebar').getByRole('button', { name: 'Logout' })).toHaveCount(0)
  await expect(page.locator('.sidebar').getByRole('button', { name: /navigation/ })).toHaveCount(1)
  await page.waitForTimeout(250)
  await captureEvidence(page, 'mobile-navigation-v067')
})

test('physical nozzle page shows exact historical use', async ({ page }) => {
  await page.route('**/api/v1/printers', (route) => route.fulfill({ json: [{
    id: 'printer-id', printer_code: 'printer-1', name: 'Workshop Printer',
    nozzle_diameter_mm: '0.4', active_nozzle_id: 'nozzle-id', active_plate_id: null,
    active_plate_surface_id: null, status: 'connected', last_seen_at: checkedAt,
    last_info_sync_at: checkedAt, record_version: 1,
  }] }))
  await page.route('**/api/v1/nozzles?include_retired=true', (route) => route.fulfill({ json: [{
    id: 'nozzle-id', nozzle_code: 'N3', printer_id: 'printer-id', diameter_mm: '0.6', material: 'Hardened steel',
    manufacturer: 'Workshop', product_name: 'High-flow', coating: null,
    purchase_date: '2026-07-21', status: 'installed', installed_printer_id: 'printer-id',
    installed_at: checkedAt, retired_at: null, notes: null, record_version: 2,
    completed_print_count: 12, completed_filament_weight_g: '4830.5',
  }] }))
  await page.route('**/api/v1/nozzles/nozzle-id/events', (route) => route.fulfill({ json: [{
    id: 'event-id', nozzle_id: 'nozzle-id', printer_id: 'printer-id', event_type: 'installed',
    performed_by: 'administrator-id', source: 'manual', notes: null, occurred_at: checkedAt,
  }] }))

  await page.goto('/nozzles')

  await expect(page.getByRole('heading', { name: 'Nozzles' })).toBeVisible()
  await expect(page.getByLabel('Select nozzle printer')).toHaveValue('printer-id')
  await expect(page.getByRole('heading', { name: '0.6 mm Hardened steel' })).toBeVisible()
  await expect(page.getByText('12', { exact: true })).toBeVisible()
  await expect(page.getByText('4,830.5 g', { exact: true })).toBeVisible()
  await page.getByRole('button').filter({ hasText: 'N3' }).click()
  await page.getByRole('button', { name: 'History' }).click()
  const lifecycle = page.getByRole('dialog', { name: 'N3 lifecycle' })
  await expect(lifecycle).toBeVisible()
  await expect(lifecycle.getByText('Installed', { exact: true })).toBeVisible()
})
