import { expect, test } from '@playwright/test'

const user = { id: 'f30ecc7d-058e-4fbe-a786-6cbfb5011100', role: 'administrator', username: 'admin', display_name: 'Administrator', is_active: true, must_change_password: false, record_version: 1 }
const userHandle = Buffer.from(user.id.replace(/-/g, ''), 'hex').toString('base64url')
const challenge = Buffer.alloc(32, 7).toString('base64url')

for (const variant of [
  { name: 'desktop', viewport: { width: 1440, height: 1050 }, theme: 'dark-navy' },
  { name: 'mobile', viewport: { width: 390, height: 844 }, theme: 'light-navy' },
]) {
  test(`Passkey login and Settings: ${variant.name}`, async ({ page }) => {
    await page.setViewportSize(variant.viewport)
    await page.addInitScript((theme) => localStorage.setItem('filament-manager-theme', theme), variant.theme)
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('WebAuthn.enable')
    await cdp.send('WebAuthn.addVirtualAuthenticator', { options: { protocol: 'ctap2', transport: 'internal', hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true } })
    let authenticated = false
    let requestedName = ''
    let registered = false
    let verified = false
    let registrationBody: Record<string, unknown> | undefined
    let authenticationBody: Record<string, unknown> | undefined
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    const keys = [
      { id: 'phone-key', name: 'My phone', created_at: '2026-10-12T13:00:00Z', last_used_at: '2026-10-12T14:00:00Z' },
      { id: 'security-key', name: 'Backup security key', created_at: '2026-10-12T13:05:00Z', last_used_at: null },
    ]
    await page.route('**/runtime-config.js', (route) => route.fulfill({ contentType: 'application/javascript', body: 'window.__FILAMENT_MANAGER_RUNTIME_CONFIG__={bugsnag:{enabled:false}};' }))
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      const path = url.pathname.replace('/api/v1', '')
      if (path === '/auth/me') return route.fulfill(authenticated ? { json: user } : { status: 401, json: { code: 'authentication_required', message: 'Sign in required' } })
      if (path === '/auth/login') { authenticated = true; return route.fulfill({ json: { user } }) }
      if (path === '/auth/logout') { authenticated = false; return route.fulfill({ status: 204 }) }
      if (path === '/auth/users') return route.fulfill({ json: [user] })
      if (path === '/auth/passkeys/availability') return route.fulfill({ json: { available: true } })
      if (path === '/auth/passkeys') return route.fulfill({ json: keys })
      if (path === '/auth/passkeys/register/options') {
        requestedName = (route.request().postDataJSON() as { name: string }).name
        return route.fulfill({ json: { challenge, rp: { id: 'localhost', name: 'Filament Manager' }, user: { id: userHandle, name: 'admin', displayName: 'Administrator' }, pubKeyCredParams: [{ type: 'public-key', alg: -7 }], authenticatorSelection: { residentKey: 'required', requireResidentKey: true, userVerification: 'required' }, attestation: 'none', timeout: 60000 } })
      }
      if (path === '/auth/passkeys/register/verify') {
        registrationBody = route.request().postDataJSON()
        registered = true
        const key = { id: 'new-key', name: requestedName, created_at: '2026-10-12T15:00:00Z', last_used_at: null }
        keys.push(key)
        return route.fulfill({ json: key })
      }
      if (path.endsWith('/remove') && path.startsWith('/auth/passkeys/')) {
        expect(route.request().postDataJSON()).toEqual({ current_password: 'example-password' })
        keys.splice(keys.findIndex((key) => path.includes(key.id)), 1)
        return route.fulfill({ status: 204 })
      }
      if (path === '/auth/passkeys/login/options') return route.fulfill({ json: { challenge, rpId: 'localhost', userVerification: 'required', timeout: 60000 } })
      if (path === '/auth/passkeys/login/verify') {
        authenticationBody = route.request().postDataJSON()
        verified = true; authenticated = true
        return route.fulfill({ json: { user } })
      }
      if (path === '/settings/operational') return route.fulfill({ json: { record_version: 1, gcode_inspection_policy: 'warn' } })
      if (path === '/settings/google') return route.fulfill({ json: { status: 'not_configured', configured: false, connected: false, client_configured: false, encryption_ready: false } })
      if (path === '/dashboard') return route.fulfill({ json: { total_spools: 0, needs_weighing: 0, low_spools: 0, empty_spools: 0, distinct_colors: 0, material_spool_counts: {}, active_spool: null, active_plate: null, active_plate_surface: null, printer_contexts: [], printer_state: { operational_status: 'unavailable', connection_status: 'unavailable', print_stats: {}, print_duration_seconds: null } } })
      if (['/notifications', '/devices', '/imports/workbook', '/printers', '/filaments', '/profiles/templates', '/spool-location-choices', '/spool-type-choices'].includes(path)) return route.fulfill({ json: [] })
      if (path.startsWith('/auth/')) errors.push(`Unexpected authentication request: ${path}`)
      return route.fulfill({ json: [] })
    })
    const evidence = process.env.FILAMENT_MANAGER_E2E_EVIDENCE_DIR
    await page.goto('/login')
    await expect(page).toHaveTitle(/Filament Manager/)
    await expect(page.getByRole('button', { name: 'Sign in with passkey' })).toBeEnabled()
    await expect(page.getByLabel('Username')).toHaveAttribute('autocomplete', 'username webauthn')
    if (evidence) await page.screenshot({ path: `${evidence}/passkey-login-${variant.name}.png`, fullPage: true })
    await page.getByLabel('Username').fill('admin')
    await page.getByLabel('Password', { exact: true }).fill('example-password')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await page.goto('/settings')
    const section = page.locator('.passkey-settings')
    await expect(section.getByRole('heading', { name: 'Passkeys', exact: true })).toBeVisible()
    await section.scrollIntoViewIfNeeded()
    if (evidence) await section.screenshot({ path: `${evidence}/passkey-settings-${variant.name}.png` })
    await section.getByRole('button', { name: 'Add passkey' }).click()
    await page.getByLabel('Passkey name').fill('This browser')
    await page.getByLabel('Current password').fill('example-password')
    if (evidence) await page.getByRole('dialog').screenshot({ path: `${evidence}/passkey-setup-${variant.name}.png` })
    await page.getByRole('button', { name: 'Create passkey' }).click()
    await expect.poll(() => registered).toBe(true)
    expect(registrationBody?.credential).toEqual(expect.objectContaining({ type: 'public-key', response: expect.objectContaining({ attestationObject: expect.any(String) }) }))
    await expect(section.getByText('This browser', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => localStorage.getItem('filament-manager.passkey-browser.v1'))).toBe('1')
    authenticated = false
    verified = false
    await page.goto('/login')
    await expect.poll(() => verified).toBe(true)
    expect(authenticationBody?.credential).toEqual(expect.objectContaining({ type: 'public-key', response: expect.objectContaining({ signature: expect.any(String), userHandle }) }))
    await expect(page).toHaveURL(/\/$/)
    authenticated = false
    verified = false
    await page.evaluate(() => localStorage.removeItem('filament-manager.passkey-browser.v1'))
    await page.addInitScript(() => { PublicKeyCredential.isConditionalMediationAvailable = async () => false })
    await page.goto('/login')
    await page.getByRole('button', { name: 'Sign in with passkey' }).click()
    await expect.poll(() => verified).toBe(true)
    await page.goto('/settings')
    await page.locator('.passkey-settings').getByRole('button', { name: 'Remove passkey This browser' }).click()
    await page.getByLabel('Current password').fill('example-password')
    await page.getByRole('button', { name: 'Remove passkey', exact: true }).click()
    await expect(page.locator('.passkey-settings').getByText('This browser', { exact: true })).toHaveCount(0)
    expect(await page.locator('vite-error-overlay').count()).toBe(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect(errors).toEqual([])
  })
}
