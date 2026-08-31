// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../context/RouterContext'
import { AppShell } from './AppShell'

vi.mock('../api/client', () => ({ apiFetch: vi.fn(() => Promise.resolve([])) }))

describe('AppShell navigation', () => {
  afterEach(cleanup)

  it('keeps Filaments primary and removes Profiles as a top-level destination', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><RouterProvider><AppShell><p>Content</p></AppShell></RouterProvider></QueryClientProvider>)

    const navigation = screen.getByRole('navigation', { name: 'Main navigation' })
    expect(screen.getByRole('link', { name: 'Filaments' }).getAttribute('href')).toBe('/filaments')
    expect(navigation.querySelector('a[href="/profiles"]')).toBeNull()
  })

  it('places Print history immediately after Printers and omits the sidebar logout action', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><RouterProvider><AppShell><p>Content</p></AppShell></RouterProvider></QueryClientProvider>)

    const links = Array.from(screen.getByRole('navigation', { name: 'Main navigation' }).querySelectorAll('a'))
    const printerIndex = links.findIndex((link) => link.getAttribute('href') === '/printers')
    expect(links[printerIndex + 1]?.getAttribute('href')).toBe('/prints')
    expect(screen.queryByRole('button', { name: 'Logout' })).toBeNull()
  })

  it('closes the notification panel only when the user clicks outside it', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><RouterProvider><AppShell><button>Outside control</button></AppShell></RouterProvider></QueryClientProvider>)

    fireEvent.click(screen.getAllByRole('button', { name: '0 unread notifications' })[0])
    expect(screen.getByRole('heading', { name: 'Notifications' })).toBeTruthy()

    fireEvent.pointerDown(screen.getByRole('heading', { name: 'Notifications' }))
    expect(screen.getByRole('heading', { name: 'Notifications' })).toBeTruthy()

    fireEvent.pointerDown(screen.getByRole('button', { name: 'Outside control' }))
    expect(screen.queryByRole('heading', { name: 'Notifications' })).toBeNull()
  })
})
