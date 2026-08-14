import { expect, test, type Page } from '@playwright/test'

const username = process.env.FILAMENT_MANAGER_E2E_USERNAME
const password = process.env.FILAMENT_MANAGER_E2E_PASSWORD

test.skip(!username || !password, 'Set isolated local-role credentials to run authenticated E2E checks')

async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Username').fill(username!)
  await page.getByLabel('Password').fill(password!)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
}

test('administrator can open the canonical dashboard and inventory', async ({ page }) => {
  await signIn(page)
  await expect(page.getByText('Total spools')).toBeVisible()
  await page.getByRole('link', { name: 'Spools' }).click()
  await expect(page.getByRole('heading', { name: 'Spools' })).toBeVisible()
  await expect(page.getByText('G6', { exact: true })).toBeVisible()
})

test('approved light, dark, and mobile weighing surfaces render', async ({ page }) => {
  await signIn(page)
  await page.evaluate(() => localStorage.setItem('filament-manager-theme', 'light'))
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/dashboard-light.png', fullPage: true })

  await page.getByRole('link', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'Dark theme' }).click()
  await page.goto('/')
  await page.screenshot({ path: '../docs/design/validation/dashboard-dark.png', fullPage: true })

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/spools')
  await expect(page.getByRole('heading', { name: 'Spools' })).toBeVisible()
  await page.getByText('AS1', { exact: true }).click()
  await page.getByRole('button', { name: 'Weigh spool' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.screenshot({ path: '../docs/design/validation/mobile-weighing.png' })
})
