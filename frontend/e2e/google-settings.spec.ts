import { expect, test, type Page } from '@playwright/test'

const user = { id: 'admin-id', username: 'admin', display_name: 'Administrator', role: 'administrator', is_active: true, must_change_password: false, record_version: 1 }

async function googleSettings(page: Page, ready: boolean, connected: boolean) {
  const calls: string[] = []
  await page.route('**/runtime-config.js', route => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() === 'POST') calls.push(path)
    if (path.endsWith('/disconnect')) connected = false
    const json = path.endsWith('/auth/me') ? user
      : path.endsWith('/auth/users') ? [user]
        : path.endsWith('/settings/google') ? { ready, connected, legacy: false, redirect_uri: 'https://filament.example.invalid/google/callback', spreadsheet_url: connected ? 'https://docs.google.com/spreadsheets/d/test/edit' : null, last_synced_at: connected ? '2026-09-07T18:00:00Z' : null, last_error: null, sync_requested: false, interval_seconds: 30 }
          : path.endsWith('/settings/operational') ? { gcode_inspection_policy: 'warn', record_version: 1 }
            : []
    await route.fulfill({ json })
  })
  return calls
}

test('Google setup is readable on desktop and mobile, with safe sync and disconnect', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const calls = await googleSettings(page, false, false)
  await page.addInitScript(() => localStorage.setItem('filament-manager-theme', 'dark-navy'))
  await page.goto('/settings')
  const panel = page.locator('article').filter({ has: page.getByRole('heading', { name: 'Google integration' }) })
  await expect(panel.getByRole('heading', { name: 'One-time Google Cloud setup' })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Connect Google', exact: true })).toBeDisabled()
  await panel.scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('google-desktop-dark.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: /^Workshop Navy Light/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light-navy')
  await panel.scrollIntoViewIfNeeded()
  await expect(panel).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await panel.screenshot({ path: info.outputPath('google-mobile-light.png') })
  expect(calls).toEqual([])
  const connectedCalls = await googleSettings(page, true, true)
  await page.reload()
  await expect(panel.getByRole('link', { name: 'Open spreadsheet' })).toBeVisible()
  await panel.getByRole('button', { name: 'Sync now' }).click()
  await expect.poll(() => connectedCalls.includes('/api/v1/settings/google/sync')).toBe(true)
  await panel.getByRole('button', { name: 'Disconnect', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Disconnect Google?' })).toBeVisible()
  expect(connectedCalls).not.toContain('/api/v1/settings/google/disconnect')
  await page.getByRole('button', { name: 'Disconnect Google', exact: true }).click()
  await expect.poll(() => connectedCalls.includes('/api/v1/settings/google/disconnect')).toBe(true)
  expect(errors).toEqual([])
})

test('OAuth callback removes sensitive query before app initialization', async ({ page }) => {
  const calls = await googleSettings(page, true, true)
  await page.goto('/google/callback?code=temporary-test-code&state=temporary-test-state-0000000000000000')
  await expect(page).toHaveURL(/\/settings\?google=connected$/)
  await expect(page.getByText('Google connected. The worker will create and populate your workbook.')).toBeVisible()
  expect(calls).toEqual(['/api/v1/settings/google/complete'])
})
