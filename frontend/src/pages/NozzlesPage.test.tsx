// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import NozzlesPage from './NozzlesPage'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({ apiFetch: apiFetchMock }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { role: 'administrator' } }) }))

const nozzle = {
  id: 'nozzle-id', nozzle_code: 'N3', printer_id: 'printer-id', diameter_mm: '0.6', material: 'Hardened steel',
  manufacturer: 'Workshop', product_name: 'High-flow', coating: null, purchase_date: null,
  status: 'installed', installed_printer_id: 'printer-id', installed_at: '2026-08-22T00:00:00Z',
  retired_at: null, notes: null, record_version: 2, completed_print_count: 12,
  completed_filament_weight_g: '4830.5',
}

describe('NozzlesPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
    window.localStorage.clear()
  })

  it('provides full nozzle actions from every catalog presentation', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/nozzles?include_retired=true') return Promise.resolve([nozzle])
      if (path === '/printers') return Promise.resolve([{ id: 'printer-id', name: 'Workshop Printer' }])
      if (path === '/nozzles/nozzle-id/events') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><NozzlesPage /></QueryClientProvider>)

    expect(await screen.findByRole('heading', { name: '0.6 mm Hardened steel' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Nozzles view'), { target: { value: 'list' } })
    fireEvent.click(screen.getAllByRole('row')[1])
    expect(screen.getByRole('dialog', { name: 'N3 details' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'History' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Edit' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Record removal' })).toBeTruthy()
  })

  it('filters the catalog and new-nozzle scope by the selected printer', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/nozzles?include_retired=true') return Promise.resolve([
        nozzle,
        { ...nozzle, id: 'nozzle-two', nozzle_code: 'N4', printer_id: 'printer-two', installed_printer_id: null },
      ])
      if (path === '/printers') return Promise.resolve([
        { id: 'printer-id', name: 'Workshop Printer' },
        { id: 'printer-two', name: 'Backup Printer' },
      ])
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><NozzlesPage /></QueryClientProvider>)

    expect(await screen.findByRole('heading', { name: '0.6 mm Hardened steel' })).toBeTruthy()
    expect(screen.queryByText('N4', { exact: true })).toBeNull()
    fireEvent.change(screen.getByLabelText('Select nozzle printer'), { target: { value: 'printer-two' } })
    expect(await screen.findByText('N4', { exact: true })).toBeTruthy()
    expect(screen.queryByText('N3', { exact: true })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Add nozzle' }))
    expect((screen.getByRole('combobox', { name: 'Printer' }) as HTMLSelectElement).value).toBe('printer-two')
  })
})
