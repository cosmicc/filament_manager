// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    window.localStorage.clear()
  })

  it('shows material identity and creates a color without losing the filament draft', async () => {
    window.scrollTo = vi.fn()
    apiFetchMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/filaments' && options?.method === 'POST') return Promise.resolve(filament)
      if (path === '/filaments') return Promise.resolve([filament])
      if (path === '/profiles') return Promise.resolve([{
        id: 'profile-id', filament_product_id: filament.id, extruder_temp_c: '215',
      }])
      if (path === '/profiles/templates') return Promise.resolve([{
        id: 'template-id', name: 'Template PLA', material_type: 'PLA', description: null,
        printer_id: 'printer-id', nozzle_id: 'nozzle-id', nozzle_diameter_mm: '0.4', filament_diameter_mm: '1.75',
        source_workstation_agent_id: null, source_cura_material_id: null, active: true,
        record_version: 1, created_at: '2026-08-18T00:00:00Z', updated_at: '2026-08-18T00:00:00Z',
        revisions: [{ id: 'revision-id', material_template_id: 'template-id', version: 1,
          status: 'published', settings: {}, checksum: null, published_at: '2026-08-18T00:00:00Z',
          record_version: 1, created_at: '2026-08-18T00:00:00Z' }],
      }])
      if (path === '/vendors') return Promise.resolve([])
      if (path.startsWith('/filament-attributes')) return Promise.resolve([])
      if (path === '/filament-colors' && options?.method === 'POST') return Promise.resolve({
        id: 'color-id', name: 'Custom', normalized_name: 'custom', color_hex: '808080',
        color_hexes: ['808080'], color_mode: 'solid', record_version: 1,
      })
      if (path === '/filament-colors') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'PLA · Midnight · Carbon fiber · Matte' })).toBeTruthy()
    expect(screen.getByText('Workshop Vendor')).toBeTruthy()
    expect(screen.queryByText('Workshop Blue')).toBeNull()
    expect(screen.getByText('± 0.02 mm')).toBeTruthy()
    expect(screen.getByText('215 °C')).toBeTruthy()
    expect(screen.queryByText('1.75 mm')).toBeNull()
    expect(screen.queryByText('1,000 g')).toBeNull()

    fireEvent.change(screen.getByLabelText('Filaments view'), { target: { value: 'list' } })
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getAllByRole('row')[1].getAttribute('tabindex')).toBe('0')
    fireEvent.change(screen.getByLabelText('Filaments view'), { target: { value: 'cards' } })

    fireEvent.click(screen.getByRole('button', { name: 'Add filament' }))
    const colorName = await screen.findByLabelText(/Color name/) as HTMLSelectElement
    expect(colorName.tagName).toBe('SELECT')
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'Keep this draft' } })
    fireEvent.change(colorName, { target: { value: '__filament_manager_new_item__' } })
    fireEvent.change(screen.getByLabelText('Color name', { selector: 'input' }), { target: { value: 'Custom' } })
    fireEvent.submit(screen.getByLabelText('Color name', { selector: 'input' }).closest('form')!)
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New Color' })).toBeNull())
    expect(colorName.value).toBe('Custom')
    expect((screen.getByLabelText('Notes') as HTMLTextAreaElement).value).toBe('Keep this draft')
    expect(apiFetchMock.mock.calls.filter(([path, options]) => path === '/filaments' && options?.method === 'POST')).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Create filament' }))
    expect(await screen.findByRole('dialog', { name: 'Create a spool?' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Add spool' }))
    await waitFor(() => expect(window.location.pathname).toBe('/spools'))
    expect(window.location.search).toBe('?create=1&filament_id=product-id')
  })
})
