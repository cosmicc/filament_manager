// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from './context/RouterContext'
import { App } from './App'

vi.mock('./context/AuthContext', () => ({
  useAuth: () => ({ user: { must_change_password: false }, loading: false }),
}))
vi.mock('./components/AppShell', () => ({
  AppShell: ({ children }: { children: unknown }) => <>{children}</>,
}))
vi.mock('./pages/PrintSettingsPage', () => ({ default: () => <h1>Print settings</h1> }))

describe('App routes', () => {
  afterEach(() => {
    cleanup()
    window.history.replaceState(null, '', '/')
  })

  it('redirects the legacy profiles route to filament print settings', async () => {
    window.history.replaceState(null, '', '/profiles')
    window.scrollTo = vi.fn()
    render(<RouterProvider><App /></RouterProvider>)

    await waitFor(() => expect(window.location.pathname).toBe('/filaments/settings'))
    expect(await screen.findByRole('heading', { name: 'Print settings' })).toBeTruthy()
  })
})
