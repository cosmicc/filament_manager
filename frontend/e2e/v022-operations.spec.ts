import { expect, test } from '@playwright/test'

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
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: user }))
  await page.route('**/api/v1/notifications**', (route) => route.fulfill({ json: [] }))
})

test('diagnostics consolidates operational status and recovery controls', async ({ page }) => {
  await page.route('**/api/v1/diagnostics', (route) => route.fulfill({ json: {
    checked_at: checkedAt,
    checks: [
      { key: 'database', label: 'Canonical database', category: 'connection', status: 'healthy', detail: 'Connected at the expected schema revision.', checked_at: checkedAt },
      { key: 'cura', label: 'Cura synchronization', category: 'synchronization', status: 'warning', detail: 'One paired workstation has not reported recently.', checked_at: checkedAt },
      { key: 'worker', label: 'Projection worker', category: 'worker', status: 'healthy', detail: 'Heartbeat received recently.', checked_at: checkedAt },
      { key: 'spools', label: 'Active spool state', category: 'operational', status: 'healthy', detail: 'Physical and projected state agree.', checked_at: checkedAt },
    ],
    queue_counts: { pending: 2, failed: 0, dead: 0 },
    job_type_counts: { 'spoolman.spool.upsert': 2 },
    error_log: [],
  } }))
  await page.route('**/api/v1/diagnostics/validation-runs', (route) => route.fulfill({ json: [] }))
  await page.route('**/api/v1/jobs?limit=100', (route) => route.fulfill({ json: [] }))

  await page.goto('/diagnostics')

  await expect(page.getByRole('heading', { name: 'Diagnostics' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Connections' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Synchronizations' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Workers and queues' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recent errors' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run validation' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Rebuild projections/ })).toBeVisible()
})

test('physical nozzle page shows exact historical use', async ({ page }) => {
  await page.route('**/api/v1/printers', (route) => route.fulfill({ json: [{
    id: 'printer-id', printer_code: 'printer-1', name: 'Workshop Printer',
    nozzle_diameter_mm: '0.4', active_nozzle_id: 'nozzle-id', active_plate_id: null,
    active_plate_surface_id: null, status: 'connected', last_seen_at: checkedAt,
    last_info_sync_at: checkedAt, record_version: 1,
  }] }))
  await page.route('**/api/v1/nozzles?include_retired=true', (route) => route.fulfill({ json: [{
    id: 'nozzle-id', nozzle_code: 'N3', diameter_mm: '0.6', material: 'Hardened steel',
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
  await expect(page.getByRole('heading', { name: '0.6 mm Hardened steel' })).toBeVisible()
  await expect(page.getByText('12', { exact: true })).toBeVisible()
  await expect(page.getByText('4,830.5 g', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'History' }).click()
  const lifecycle = page.getByRole('dialog', { name: 'N3 lifecycle' })
  await expect(lifecycle).toBeVisible()
  await expect(lifecycle.getByText('Installed', { exact: true })).toBeVisible()
})
