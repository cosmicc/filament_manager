// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'

const mocks = vi.hoisted(() => ({ login: vi.fn(), passkey: vi.fn(), supported: vi.fn(), recognized: vi.fn(), conditional: vi.fn(), fetch: vi.fn() }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ login: mocks.login, loginWithPasskey: mocks.passkey }) }))
vi.mock('../api/client', async (original) => ({ ...await original<typeof import('../api/client')>(), apiFetch: mocks.fetch }))
vi.mock('../lib/passkeys', async (original) => ({ ...await original<typeof import('../lib/passkeys')>(), supportsPasskeys: mocks.supported, recognizedPasskeyBrowser: mocks.recognized, supportsPasskeyAutofill: mocks.conditional }))
vi.mock('../lib/version', () => ({ APP_VERSION: '0.5.6' }))

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.supported.mockReturnValue(false)
    mocks.recognized.mockReturnValue(false)
    mocks.conditional.mockResolvedValue(true)
    mocks.fetch.mockResolvedValue({ available: true })
    mocks.passkey.mockResolvedValue(undefined)
    mocks.login.mockResolvedValue(undefined)
  })
  afterEach(cleanup)
  it('shows the version and password fallback on unsupported browsers', () => {
    render(<LoginPage />)
    expect(screen.getByText('Filament Manager v0.5.6')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Sign in with passkey' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByLabelText('Username').getAttribute('autocomplete')).toBe('username webauthn')
  })
  it('starts conditional autofill without requiring browser recognition', async () => {
    mocks.supported.mockReturnValue(true)
    render(<LoginPage />)
    await waitFor(() => expect(mocks.passkey).toHaveBeenCalledTimes(1))
    expect(mocks.passkey.mock.calls[0][1]).toBe(true)
  })
  it('makes one automatic attempt on a recognized desktop or mobile browser', async () => {
    mocks.supported.mockReturnValue(true)
    mocks.recognized.mockReturnValue(true)
    const { rerender } = render(<LoginPage />)
    await waitFor(() => expect(mocks.passkey).toHaveBeenCalledTimes(1))
    rerender(<LoginPage />)
    expect(mocks.passkey).toHaveBeenCalledTimes(1)
    expect(mocks.passkey.mock.calls[0][1]).toBe(false)
  })
  it('keeps automatic failure quiet and permits an explicit retry', async () => {
    mocks.supported.mockReturnValue(true)
    mocks.recognized.mockReturnValue(true)
    mocks.passkey.mockRejectedValue(new DOMException('cancelled', 'NotAllowedError'))
    render(<LoginPage />)
    await waitFor(() => expect(mocks.passkey).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Sign in with passkey' }))
    await waitFor(() => expect(mocks.passkey).toHaveBeenCalledTimes(2))
    expect(await screen.findByRole('alert')).toHaveTextContent('cancelled or timed out')
  })
  it('aborts a pending ceremony before password login and on unmount', async () => {
    mocks.supported.mockReturnValue(true)
    mocks.passkey.mockImplementation((signal: AbortSignal) => new Promise<void>((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))))
    const { unmount } = render(<LoginPage />)
    await waitFor(() => expect(mocks.passkey).toHaveBeenCalledTimes(1))
    const signal = mocks.passkey.mock.calls[0][0] as AbortSignal
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: /^Sign in$/ }))
    await waitFor(() => expect(mocks.login).toHaveBeenCalledWith('admin', 'password'))
    expect(signal.aborted).toBe(true)
    unmount()
  })
  it('does not start authentication when server HTTPS readiness is unavailable', async () => {
    mocks.supported.mockReturnValue(true)
    mocks.fetch.mockResolvedValue({ available: false })
    render(<LoginPage />)
    await waitFor(() => expect(mocks.fetch).toHaveBeenCalled())
    expect(mocks.passkey).not.toHaveBeenCalled()
  })
})
