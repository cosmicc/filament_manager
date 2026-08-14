// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SpoolsPage from './SpoolsPage'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({
  apiFetch: apiFetchMock,
  ApiClientError: class ApiClientError extends Error {},
  idempotencyKey: vi.fn(() => 'test-key'),
}))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'operator-id',
      username: 'operator',
      display_name: 'Operator',
      role: 'operator',
      is_active: true,
      record_version: 1,
      completed_print_count: 0,
    },
  }),
}))

const spool = {
  id: 'spool-id',
  spool_code: 'FM-001',
  filament_product_id: 'product-id',
  material_type: 'PLA',
  filler: null,
  finish: null,
  color_name: 'Blue',
  color_hex: '2244AA',
  vendor_name: 'Test Vendor',
  product_name: 'Workshop PLA',
  nominal_net_mass_g: '1000',
  tare_mass_g: '200',
  remaining_mass_expected_g: '800',
  remaining_mass_measured_g: null,
  remaining_mass_effective_g: '800',
  remaining_percent: '80',
  weight_confidence: 'estimated',
  status: 'in_stock',
  location: 'PLA-1',
  spoolman_id: 17,
  active_printer_id: null,
  last_measurement_at: null,
  notes: null,
  archived: false,
  record_version: 1,
  completed_print_count: 0,
}

describe('SpoolsPage', () => {
  afterEach(() => {
    apiFetchMock.mockReset()
  })

  it('requests a physical load without presenting the target as active early', async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path.startsWith('/spools?')) return Promise.resolve({ items: [spool], total: 1, limit: 200, offset: 0 })
      if (path === '/filaments') return Promise.resolve([])
      if (path === '/spools/spool-id/set-active' && options?.method === 'POST') {
        return Promise.resolve({ status: 'change_queued' })
      }
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <SpoolsPage />
      </QueryClientProvider>,
    )

    fireEvent.click(await screen.findByText('FM-001'))
    fireEvent.click(await screen.findByRole('button', { name: 'Load spool' }))

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith('/spools/spool-id/set-active', { method: 'POST' })
    })
    expect(await screen.findByText(/Load request sent to Fluidd/)).toBeTruthy()
    expect(screen.getByText('Not active')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Set active' })).toBeNull()
  })
})
