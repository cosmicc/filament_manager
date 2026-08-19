// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../context/RouterContext'
import FilamentsPage from './FilamentsPage'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({ apiFetch: apiFetchMock }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'operator' } }),
}))

const filament = {
  id: 'product-id',
  vendor_id: 'vendor-id',
  vendor_name: 'Workshop Vendor',
  material_type: 'PLA',
  filler: 'Carbon fiber',
  finish: 'Matte',
  color_name: 'Midnight',
  color_hex: '112233',
  color_mode: 'solid',
  color_hexes: ['112233'],
  product_name: 'Workshop Blue',
  diameter_mm: '1.75',
  tolerance_mm: '0.02',
  density_g_cm3: '1.24',
  nominal_net_mass_g: '1000',
  notes: null,
  material_template_revision_id: 'revision-id',
  archived: false,
  color_editable: true,
  record_version: 1,
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider><FilamentsPage /></RouterProvider>
    </QueryClientProvider>,
  )
}

describe('FilamentsPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
  })

  it('uses the requested three-line identity and retains manual-entry focus', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/filaments') return Promise.resolve([filament])
      if (path === '/profiles/templates') return Promise.resolve([{
        id: 'template-id', name: 'Template PLA', material_type: 'PLA', description: null,
        printer_id: 'printer-id', nozzle_diameter_mm: '0.4', filament_diameter_mm: '1.75',
        source_workstation_agent_id: null, source_cura_material_id: null, active: true,
        record_version: 1, created_at: '2026-08-18T00:00:00Z', updated_at: '2026-08-18T00:00:00Z',
        revisions: [{ id: 'revision-id', material_template_id: 'template-id', version: 1,
          status: 'published', settings: {}, checksum: null, published_at: '2026-08-18T00:00:00Z',
          record_version: 1, created_at: '2026-08-18T00:00:00Z' }],
      }])
      if (path === '/vendors') return Promise.resolve([])
      if (path === '/filament-colors') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'PLA · Midnight · Workshop Blue' })).toBeTruthy()
    expect(screen.getByText('Workshop Vendor')).toBeTruthy()
    expect(screen.getByText('Carbon fiber / Matte')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Add filament' }))
    const colorName = await screen.findByLabelText(/Color name/) as HTMLInputElement
    colorName.focus()
    for (const value of ['C', 'Cu', 'Cus', 'Cust', 'Custom']) {
      fireEvent.change(colorName, { target: { value } })
      expect(document.activeElement).toBe(colorName)
    }
    expect(colorName.value).toBe('Custom')
  })
})
