// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SpoolsPage from './SpoolsPage'
import { RouterProvider } from '../context/RouterContext'

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
  purchase_source: 'Local supplier',
  purchase_date: '2026-08-20',
  purchase_cost: '15.00',
  cost_per_gram: '0.015000',
  currency: 'USD',
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
    cleanup()
    apiFetchMock.mockReset()
    window.localStorage.clear()
    window.history.replaceState(null, '', '/spools')
  })

  window.scrollTo = vi.fn()

  it('requests a physical load without presenting the target as active early', async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path.startsWith('/spools?')) return Promise.resolve({ items: [spool], total: 1, limit: 200, offset: 0 })
      if (path === '/filaments') return Promise.resolve([])
      if (path === '/profiles/templates') return Promise.resolve([])
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
        <RouterProvider><SpoolsPage /></RouterProvider>
      </QueryClientProvider>,
    )

    fireEvent.click(await screen.findByText('FM-001'))
    expect(screen.getByRole('dialog', { name: 'FM-001 details' })).toBeTruthy()
    expect(screen.queryByText('Select a spool')).toBeNull()
    expect(screen.queryByText(/No filler/i)).toBeNull()
    expect(screen.queryByText(/Standard finish/i)).toBeNull()
    fireEvent.click(await screen.findByRole('button', { name: 'Load spool' }))

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith('/spools/spool-id/set-active', { method: 'POST' })
    })
    expect(await screen.findByText(/Load request sent to Fluidd/)).toBeTruthy()
    expect(screen.getByText('Not active')).toBeTruthy()
    expect(screen.getAllByText('1.5¢/g').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Set active' })).toBeNull()
  })

  it('opens a new spool with the just-created filament selected', async () => {
    window.history.replaceState(null, '', '/spools?create=1&filament_id=product-id')
    apiFetchMock.mockImplementation((path: string) => {
      if (path.startsWith('/spools?')) return Promise.resolve({ items: [], total: 0, limit: 200, offset: 0 })
      if (path === '/filaments') return Promise.resolve([{ ...spool, id: 'product-id', nominal_net_mass_g: '750' }])
      if (path === '/printers') return Promise.resolve([])
      if (path === '/profiles/templates' || path.startsWith('/spool-tare-suggestions')) return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(<QueryClientProvider client={queryClient}><RouterProvider><SpoolsPage /></RouterProvider></QueryClientProvider>)

    expect(await screen.findByRole('dialog', { name: 'Add a physical spool' })).toBeTruthy()
    expect((screen.getByLabelText('Filament product') as HTMLSelectElement).value).toBe('product-id')
    expect((screen.getAllByRole('spinbutton')[0] as HTMLInputElement).value).toBe('750')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(window.location.search).toBe('')
  })

  it('opens a location link and previews tare changes without silently overriding remaining mass', async () => {
    window.history.replaceState(null, '', '/spools?spool_id=spool-id')
    const weighed = { ...spool, remaining_mass_effective_g: '875', last_measurement_at: '2026-09-05T00:00:00Z' }
    apiFetchMock.mockImplementation((path: string, options?: { method?: string; body?: string }) => {
      if (path.startsWith('/spools?')) return Promise.resolve({ items: [], total: 0, limit: 200, offset: 0 })
      if (path === '/spools/spool-id') return Promise.resolve(options?.method === 'PATCH' ? { ...weighed, tare_mass_g: '240', remaining_mass_effective_g: '835' } : weighed)
      if (path === '/spools/spool-id/mass-basis') return Promise.resolve({ last_gross_mass_g: '1200', adjustment_since_weighing_g: '-125' })
      if (path.startsWith('/spool-tare-suggestions')) return Promise.resolve([{ tare_mass_g: '240', nominal_net_mass_g: '1000', spool_count: 3 }])
      if (path === '/filaments') return Promise.resolve([{ ...spool, id: 'product-id' }])
      if (path === '/printers' || path === '/profiles/templates') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><RouterProvider><SpoolsPage /></RouterProvider></QueryClientProvider>)
    expect(await screen.findByRole('dialog', { name: 'FM-001 details' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Edit spool' }))
    await waitFor(() => expect((screen.getByLabelText(/Current filament remaining/) as HTMLInputElement).value).toBe('875'))
    fireEvent.change(screen.getByLabelText(/Empty spool weight \(g\)/), { target: { value: '250' } })
    expect((screen.getByLabelText(/Current filament remaining/) as HTMLInputElement).value).toBe('825')
    const total = screen.getByLabelText(/Current total spool weight/) as HTMLInputElement
    expect(total.value).toBe('1075')
    expect(total.readOnly).toBe(true)
    expect(screen.getByLabelText('Location').tagName).toBe('SELECT')
    expect(screen.getByRole('option', { name: 'New Location' })).toBeTruthy()
    expect(screen.queryByLabelText(/Bucket or location/)).toBeNull()
    fireEvent.change(await screen.findByLabelText('Suggested empty-spool weight'), { target: { value: '0' } })
    expect((screen.getByLabelText(/Current filament remaining/) as HTMLInputElement).value).toBe('835')
    fireEvent.click(screen.getByRole('button', { name: 'Save spool' }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith('/spools/spool-id', expect.objectContaining({ method: 'PATCH' })))
    const call = apiFetchMock.mock.calls.find((entry) => entry[1]?.method === 'PATCH')
    const payload = JSON.parse(call?.[1].body ?? '{}')
    expect(payload.tare_mass_g).toBe('240')
    expect(payload).not.toHaveProperty('remaining_mass_g')
    expect(payload).not.toHaveProperty('current_total_mass_g')
  })

  it('preserves precise saved weights when only the location changes', async () => {
    const precise = { ...spool, tare_mass_g: '200.045', nominal_net_mass_g: '1000.025', remaining_mass_effective_g: '800.123' }
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/spool-location-choices') return Promise.resolve([{ name: 'Bucket 12' }])
      if (path.startsWith('/spools?')) return Promise.resolve({ items: [precise], total: 1, limit: 200, offset: 0 })
      if (path === '/spools/spool-id') return Promise.resolve(precise)
      if (path === '/spools/spool-id/mass-basis') return Promise.resolve({ last_gross_mass_g: null, adjustment_since_weighing_g: null })
      if (path.startsWith('/spool-tare-suggestions') || path === '/printers' || path === '/profiles/templates') return Promise.resolve([])
      if (path === '/filaments') return Promise.resolve([{ ...spool, id: 'product-id' }])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><RouterProvider><SpoolsPage /></RouterProvider></QueryClientProvider>)
    fireEvent.click(await screen.findByText('FM-001'))
    fireEvent.click(screen.getByRole('button', { name: 'Edit spool' }))
    await waitFor(() => expect((screen.getByRole('button', { name: 'Save spool' }) as HTMLButtonElement).disabled).toBe(false))
    await screen.findByRole('option', { name: 'Bucket 12' })
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'Bucket 12' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save spool' }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith('/spools/spool-id', expect.objectContaining({ method: 'PATCH' })))
    const call = apiFetchMock.mock.calls.find((entry) => entry[1]?.method === 'PATCH')
    const payload = JSON.parse(call?.[1].body ?? '{}')
    expect(payload.tare_mass_g).toBe('200.045')
    expect(payload.nominal_net_mass_g).toBe('1000.025')
    expect(payload).not.toHaveProperty('remaining_mass_g')
  })

  it('keeps a full-weight spool save successful when a subsequent refresh fails', async () => {
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/spools' && options?.method === 'POST') return Promise.resolve(spool)
      if (path.startsWith('/spools?')) return Promise.resolve({ items: [], total: 0, limit: 200, offset: 0 })
      if (path === '/filaments') return Promise.resolve([{ ...spool, id: 'product-id' }])
      return Promise.resolve([])
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    vi.spyOn(client, 'invalidateQueries').mockRejectedValue(new Error('Refresh failed after save'))
    render(<QueryClientProvider client={client}><RouterProvider><SpoolsPage /></RouterProvider></QueryClientProvider>)
    await waitFor(() => expect((screen.getByRole('button', { name: 'Add spool' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(await screen.findByRole('button', { name: 'Add spool' }))
    await screen.findByRole('option', { name: /PLA.*Blue/ })
    fireEvent.change(screen.getByLabelText('Spool code'), { target: { value: 'NEW-WEIGHED' } })
    fireEvent.change(screen.getByLabelText(/Full spool scale weight/), { target: { value: '1200' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create spool' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByText('Refresh failed after save')).toBeNull()
    const posts = apiFetchMock.mock.calls.filter((call) => call[1]?.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(JSON.parse(posts[0][1].body)).toMatchObject({ initial_gross_mass_g: '1200', spool_code: 'NEW-WEIGHED' })
  })

  it('combines the template-derived filament type filter with text search', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path.startsWith('/spools?')) return Promise.resolve({ items: [spool], total: 1, limit: 200, offset: 0 })
      if (path === '/profiles/templates') return Promise.resolve([{ id: '1', material_type: 'PLA' }, { id: '2', material_type: 'pla' }, { id: '3', material_type: 'PETG' }])
      if (path === '/filaments' || path === '/printers') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><RouterProvider><SpoolsPage /></RouterProvider></QueryClientProvider>)
    await screen.findByRole('option', { name: 'PETG' })
    const filter = screen.getByLabelText('Filter by filament type') as HTMLSelectElement
    expect(filter.value).toBe('')
    expect(filter.options.length).toBe(3)
    fireEvent.change(filter, { target: { value: 'petg' } })
    fireEvent.change(screen.getByLabelText('Search spools'), { target: { value: 'Carbon fiber' } })
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith('/spools?limit=200&search=Carbon%20fiber&material=petg'))
  })
})
