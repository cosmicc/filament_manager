import { expect, test, type Page } from '@playwright/test'

async function openLogin(page: Page, width: number, height: number) {
  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  await page.route('**/runtime-config.js', async (route) => {
    await route.fulfill({
      contentType: 'application/javascript',
      body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};',
    })
  })
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: 'null' })
  })
  await page.setViewportSize({ width, height })
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'The ultimate 3D printing filament and Cura manager' })).toBeVisible()
  return consoleErrors
}

test('desktop login content begins at the artwork top with a compact brand gap', async ({ page }) => {
  const consoleErrors = await openLogin(page, 1440, 900)

  const brand = await page.locator('.login-brand').boundingBox()
  const artwork = await page.locator('.login-art').boundingBox()
  const eyebrow = await page.getByText('PRINT OPERATIONS').boundingBox()

  expect(brand).not.toBeNull()
  expect(artwork).not.toBeNull()
  expect(eyebrow).not.toBeNull()
  expect(Math.abs(brand!.y - artwork!.y)).toBeLessThanOrEqual(1)
  expect(eyebrow!.y - (brand!.y + brand!.height)).toBeGreaterThanOrEqual(18)
  expect(eyebrow!.y - (brand!.y + brand!.height)).toBeLessThanOrEqual(22)
  await page.getByLabel('Username').fill('layout-check')
  await expect(page.getByLabel('Username')).toHaveValue('layout-check')
  expect(consoleErrors).toEqual([])
})

test('mobile login content keeps the compact top alignment', async ({ page }) => {
  const consoleErrors = await openLogin(page, 390, 844)

  const brand = await page.locator('.login-brand').boundingBox()
  const eyebrow = await page.getByText('PRINT OPERATIONS').boundingBox()

  expect(brand).not.toBeNull()
  expect(eyebrow).not.toBeNull()
  expect(brand!.y).toBeLessThanOrEqual(18)
  expect(eyebrow!.y - (brand!.y + brand!.height)).toBeGreaterThanOrEqual(18)
  expect(eyebrow!.y - (brand!.y + brand!.height)).toBeLessThanOrEqual(22)
  expect(consoleErrors).toEqual([])
})
