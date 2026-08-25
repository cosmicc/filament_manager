// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../context/RouterContext'
import { AppShell } from './AppShell'

vi.mock('../api/client', () => ({ apiFetch: vi.fn(() => Promise.resolve([])) }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ logout: vi.fn() }) }))

describe('AppShell navigation', () => {
  afterEach(cleanup)

  it('keeps Filaments primary and removes Profiles as a top-level destination', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><RouterProvider><AppShell><p>Content</p></AppShell></RouterProvider></QueryClientProvider>)

    const navigation = screen.getByRole('navigation', { name: 'Main navigation' })
    expect(screen.getByRole('link', { name: 'Filaments' }).getAttribute('href')).toBe('/filaments')
    expect(navigation.querySelector('a[href="/profiles"]')).toBeNull()
  })
})
