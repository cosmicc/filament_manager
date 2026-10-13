// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PasskeySettingsPanel } from './PasskeySettingsPanel'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), register: vi.fn() }))
vi.mock('../api/client', async (original) => ({ ...await original<typeof import('../api/client')>(), apiFetch: mocks.fetch }))
vi.mock('../lib/passkeys', async (original) => ({ ...await original<typeof import('../lib/passkeys')>(), registerPasskey: mocks.register, supportsPasskeys: () => true }))
const key = { id: 'key-1', name: 'My phone', created_at: '2026-10-12T12:00:00Z', last_used_at: null }
function mount() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PasskeySettingsPanel /></QueryClientProvider>)
}

describe('PasskeySettingsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetch.mockImplementation(async (path: string) => path.endsWith('/availability') ? { available: true } : path.endsWith('/remove') ? undefined : [key])
    mocks.register.mockResolvedValue(key)
  })
  afterEach(cleanup)
  it('lists friendly labels without exposing credential material', async () => {
    mount()
    expect(await screen.findByText('My phone')).toBeVisible()
    expect(screen.getByText('Not used to sign in yet')).toBeVisible()
  })
  it('requires a name and password for enrollment and clears password after success', async () => {
    mount()
    await screen.findByText('My phone')
    fireEvent.click(screen.getByRole('button', { name: 'Add passkey' }))
    fireEvent.change(screen.getByLabelText('Passkey name'), { target: { value: 'My laptop' } })
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'secret password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create passkey' }))
    await waitFor(() => expect(mocks.register).toHaveBeenCalledWith('My laptop', 'secret password', expect.any(AbortSignal)))
    expect(await screen.findByText('Passkey added. You can use it for your next sign-in.')).toBeVisible()
    expect(screen.queryByLabelText('Current password')).toBeNull()
  })
  it('confirms removal with the current password in a separate dialog', async () => {
    mount()
    await screen.findByText('My phone')
    fireEvent.click(screen.getByRole('button', { name: 'Remove passkey My phone' }))
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'secret password' } })
    fireEvent.click(screen.getByRole('button', { name: /^Remove passkey$/ }))
    await waitFor(() => expect(mocks.fetch).toHaveBeenCalledWith('/auth/passkeys/key-1/remove', expect.objectContaining({ method: 'POST', body: JSON.stringify({ current_password: 'secret password' }) })))
    expect(await screen.findByText(/Other browser sessions were signed out/)).toBeVisible()
  })
})
