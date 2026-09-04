// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../context/RouterContext'
import PrintSettingsPage from './PrintSettingsPage'

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ apiFetch: apiFetchMock }))

describe('PrintSettingsPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
    window.history.replaceState(null, '', '/')
  })

  it('shows exact filament, printer, nozzle, comparison, edit, and export actions', async () => {
    window.history.replaceState(null, '', '/filaments/settings')
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/profiles') return Promise.resolve([{
        id: 'profile-id', filament_product_id: 'filament-id', printer_id: 'printer-id',
        nozzle_diameter_mm: '0.6', extruder_temp_c: '220', bed_temp_c: '65',
        override_count: 2, base_template_name: 'Template PLA 0.6', cura_settings: { speed_print: '60' },
      }])
      if (path === '/filaments') return Promise.resolve([{
        id: 'filament-id', vendor_name: 'Workshop', material_type: 'PLA', color_name: 'Blue',
        filler: 'Carbon Fiber', finish: 'Matte',
      }])
      if (path === '/printers') return Promise.resolve([{ id: 'printer-id', name: 'Printer A' }])
      if (path === '/build-plates' || path === '/profiles/templates?include_inactive=true' || path === '/profiles/cura-settings/catalog') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><RouterProvider><PrintSettingsPage /></RouterProvider></QueryClientProvider>)

    expect(await screen.findByRole('heading', { name: 'Print settings' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Catalog' }).getAttribute('href')).toBe('/filaments')
    expect(await screen.findByText('Printer A · 0.6 mm')).toBeTruthy()
    expect(screen.getByText('2 customized')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Compare Workshop · PLA · Blue · Carbon Fiber · Matte/ })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Open Workshop · PLA · Blue · Carbon Fiber · Matte/ }).getAttribute('href')).toBe('/filaments/filament-id')
    expect(screen.getByRole('link', { name: /Download Workshop · PLA · Blue · Carbon Fiber · Matte/ }).getAttribute('href')).toBe('/api/v1/profiles/profile-id/exports/cura')
  })
})
