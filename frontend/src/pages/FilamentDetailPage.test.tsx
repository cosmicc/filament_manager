// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClientError } from '../api/client'
import { RouterProvider } from '../context/RouterContext'
import FilamentDetailPage from './FilamentDetailPage'

const apiFetchMock = vi.hoisted(() => vi.fn())
const authState = vi.hoisted(() => ({ role: 'operator' }))

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  apiFetch: apiFetchMock,
}))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: authState.role } }),
}))

const settings = {
  chamber_temp_c: null, extruder_temp_c: '215', bed_temp_c: '60', initial_bed_temp_c: '65', flow_percent: '100',
  print_speed_mm_s: '60', outer_wall_speed_mm_s: '30', inner_wall_speed_mm_s: '60',
  infill_speed_mm_s: '60', top_bottom_speed_mm_s: '30', initial_layer_speed_mm_s: '20',
  travel_speed_mm_s: '150', support_speed_mm_s: '50', retraction_distance_mm: '0.8',
  retraction_speed_mm_s: '35', retraction_prime_speed_mm_s: '35', cooling_enabled: true,
  cooling_min_percent: '20', cooling_max_percent: '100', support_overhang_angle_deg: '50',
  tree_max_branch_angle_deg: null, pressure_advance: '0.04',
  ironing_flow_percent: null, ironing_speed_mm_s: null, ironing_line_spacing_mm: null,
  filament_density_g_cm3: '1.24', preferred_build_plate_surface_id: null, cura_extensions: {},
}

const filament = {
  id: 'product-id', vendor_id: null, vendor_name: null, material_type: 'PLA', filler: null,
  finish: null, color_name: 'Blue', color_hex: '2244AA', color_mode: 'solid',
  color_hexes: ['2244AA'], product_name: 'Workshop PLA', diameter_mm: '1.75',
  tolerance_mm: null, density_g_cm3: '1.24', nominal_net_mass_g: '1000', notes: null,
  material_template_revision_id: 'revision-04', archived: false, color_editable: true,
  record_version: 1,
}

function template(id: string, material: string, nozzle: string) {
  return {
    id, name: `Template ${material} ${nozzle}`, material_type: material, description: null,
    printer_id: 'printer-id', nozzle_diameter_mm: nozzle, filament_diameter_mm: '1.75',
    source_workstation_agent_id: null, source_cura_material_id: null, active: true,
    record_version: 1, created_at: '2026-08-18T00:00:00Z', updated_at: '2026-08-18T00:00:00Z',
    revisions: [{ id: `revision-${nozzle.replace('.', '')}`, material_template_id: id, version: 1,
      status: 'published', settings, checksum: null, published_at: '2026-08-18T00:00:00Z',
      record_version: 1, created_at: '2026-08-18T00:00:00Z' }],
  }
}

function profile(id: string, nozzle: string, version: number, overrides: Record<string, unknown> = {}) {
  return {
    ...settings, ...overrides, id, filament_product_id: filament.id, printer_id: 'printer-id',
    nozzle_diameter_mm: nozzle, version, status: 'published', cura_settings: { material_print_temperature: settings.extruder_temp_c },
    published_at: '2026-08-18T00:00:00Z', checksum: null, record_version: 1,
    base_template_revision_id: `revision-${nozzle.replace('.', '')}`, setting_overrides: overrides,
    override_keys: Object.keys(overrides), override_count: Object.keys(overrides).length,
    inheritance_status: Object.keys(overrides).length ? 'customized' : 'inherited',
    base_template_id: `template-${nozzle.replace('.', '')}`, base_template_name: `Template PLA ${nozzle}`,
    base_template_version: 1, base_template_settings: settings,
    latest_template_revision_id: `revision-${nozzle.replace('.', '')}`, latest_template_version: 1,
    template_update_changes: [], source_workstation_agent_id: null, source_cura_material_id: null,
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={queryClient}><RouterProvider><FilamentDetailPage /></RouterProvider></QueryClientProvider>)
}

describe('FilamentDetailPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
    authState.role = 'operator'
    window.history.replaceState(null, '', '/')
  })

  it('renders and edits each current printer/nozzle profile by exact ID', async () => {
    window.history.replaceState(null, '', '/filaments/product-id')
    const profiles = [profile('profile-04', '0.4', 8), profile('profile-06', '0.6', 2, { bed_temp_c: '65' })]
    const saves: string[] = []
    apiFetchMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === '/filaments/product-id') return Promise.resolve(filament)
      if (path === '/profiles') return Promise.resolve(profiles)
      if (path === '/profiles/templates?include_inactive=false') return Promise.resolve([
        template('template-04', 'PLA', '0.4'), template('template-06', 'PLA', '0.6'),
      ])
      if (path === '/printers') return Promise.resolve([{ id: 'printer-id', name: 'Printer A' }])
      if (path === '/filament-colors' || path === '/vendors' || path === '/build-plates' || path === '/profiles/cura-settings/catalog') return Promise.resolve([])
      if (path.startsWith('/profiles/profile-') && options?.method === 'PUT') {
        saves.push(path)
        return Promise.resolve(profiles.find((item) => path.includes(item.id)))
      }
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    renderPage()

    expect(await screen.findByRole('heading', { name: '0.4 mm nozzle' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '0.6 mm nozzle' })).toBeTruthy()
    expect(screen.getByText('8', { selector: 'dd' })).toBeTruthy()
    expect(screen.getByText('2', { selector: 'dd' })).toBeTruthy()

    const card06 = screen.getByRole('heading', { name: '0.6 mm nozzle' }).closest('article')
    expect(card06).not.toBeNull()
    fireEvent.click(within(card06 as HTMLElement).getByRole('button', { name: 'Edit settings' }))
    expect(await screen.findByRole('dialog', { name: 'Edit Printer A · 0.6 mm settings' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(saves).toEqual(['/profiles/profile-06/settings']))

    const card04 = screen.getByRole('heading', { name: '0.4 mm nozzle' }).closest('article')
    fireEvent.click(within(card04 as HTMLElement).getByRole('button', { name: 'Edit settings' }))
    expect(await screen.findByRole('dialog', { name: 'Edit Printer A · 0.4 mm settings' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(saves).toEqual(['/profiles/profile-06/settings', '/profiles/profile-04/settings']))
  })

  it('separates product editing and offers only compatible missing scopes', async () => {
    window.history.replaceState(null, '', '/filaments/product-id')
    let addedBody: Record<string, unknown> | null = null
    const currentProfiles = [profile('profile-04', '0.4', 8)]
    apiFetchMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === '/filaments/product-id') return Promise.resolve(filament)
      if (path === '/profiles') return Promise.resolve(currentProfiles)
      if (path === '/profiles/templates?include_inactive=false') return Promise.resolve([
        template('template-04', 'PLA', '0.4'), template('template-06', 'PLA', '0.6'),
        template('template-08', 'ABS', '0.8'),
      ])
      if (path === '/printers') return Promise.resolve([{ id: 'printer-id', name: 'Printer A' }])
      if (path === '/filament-colors' || path === '/vendors' || path === '/build-plates' || path === '/profiles/cura-settings/catalog') return Promise.resolve([])
      if (path === '/profiles/from-template' && options?.method === 'POST') {
        addedBody = JSON.parse(String(options.body)) as Record<string, unknown>
        currentProfiles.push(profile('profile-06', '0.6', 1))
        return Promise.resolve(currentProfiles[1])
      }
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit product' }))
    const productDialog = screen.getByRole('dialog', { name: 'Edit filament product' })
    expect(within(productDialog).queryByLabelText(/Linked material template/)).toBeNull()
    fireEvent.click(within(productDialog).getByRole('button', { name: 'Cancel' }))

    fireEvent.click(screen.getByRole('button', { name: 'Add print settings' }))
    const selector = screen.getByLabelText('Printer and nozzle') as HTMLSelectElement
    expect(Array.from(selector.options).map((option) => option.text)).toEqual([
      'Template PLA 0.6 · Printer A · 0.6 mm',
    ])
    fireEvent.click(screen.getByRole('button', { name: 'Add settings' }))
    await waitFor(() => expect(addedBody).toEqual({
      filament_product_id: 'product-id', material_template_revision_id: 'revision-06',
    }))
  })

  it('keeps profile inspection actions read-only for viewers', async () => {
    authState.role = 'viewer'
    window.history.replaceState(null, '', '/filaments/product-id')
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/filaments/product-id') return Promise.resolve(filament)
      if (path === '/profiles') return Promise.resolve([profile('profile-04', '0.4', 8)])
      if (path === '/profiles/templates?include_inactive=false') return Promise.resolve([
        template('template-04', 'PLA', '0.4'), template('template-06', 'PLA', '0.6'),
      ])
      if (path === '/printers') return Promise.resolve([{ id: 'printer-id', name: 'Printer A' }])
      if (path === '/filament-colors' || path === '/vendors' || path === '/build-plates' || path === '/profiles/cura-settings/catalog') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    renderPage()

    expect(await screen.findByRole('heading', { name: '0.4 mm nozzle' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Edit product' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Edit settings' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Add print settings' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Compare' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Export Cura JSON' }).getAttribute('href')).toBe(
      '/api/v1/profiles/profile-04/exports/cura',
    )
  })

  it('uses a derived Rainbow name without an editable display name or resubmitted palette', async () => {
    window.history.replaceState(null, '', '/filaments/product-id')
    const rainbow = {
      ...filament,
      color_name: 'Rainbow',
      color_hex: 'E53935',
      color_mode: 'rainbow',
      color_hexes: ['E53935', 'FB8C00', 'FDD835', '43A047', '1E88E5', '8E24AA'],
    }
    const updateBodies: Record<string, unknown>[] = []
    apiFetchMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === '/filaments/product-id' && options?.method === 'PATCH') {
        updateBodies.push(JSON.parse(String(options.body)) as Record<string, unknown>)
        return Promise.resolve({ ...rainbow, product_name: null, record_version: 2 })
      }
      if (path === '/filaments/product-id') return Promise.resolve(rainbow)
      if (path === '/profiles') return Promise.resolve([profile('profile-04', '0.4', 8)])
      if (path === '/profiles/templates?include_inactive=false') return Promise.resolve([template('template-04', 'PLA', '0.4')])
      if (path === '/printers') return Promise.resolve([{ id: 'printer-id', name: 'Printer A' }])
      if (path === '/filament-colors' || path === '/vendors' || path === '/build-plates' || path === '/profiles/cura-settings/catalog') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit product' }))
    expect(screen.queryByLabelText('Display name')).toBeNull()
    expect(screen.getByRole('heading', { level: 1, name: 'PLA · Rainbow' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Create spool from filament' }).getAttribute('href')).toBe(
      '/spools?create=1&filament_id=product-id',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Save filament' }))

    await waitFor(() => expect(updateBodies).toHaveLength(1))
    expect(updateBodies[0]).not.toHaveProperty('product_name')
    expect(updateBodies[0].color_mode).toBe('rainbow')
    expect(updateBodies[0].color_hexes).toEqual([])
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Edit filament product' })).toBeNull())
  })

  it('highlights, explains, and focuses a rejected product field', async () => {
    window.history.replaceState(null, '', '/filaments/product-id')
    Element.prototype.scrollIntoView = vi.fn()
    apiFetchMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === '/filaments/product-id' && options?.method === 'PATCH') {
        return Promise.reject(new ApiClientError(
          422,
          'validation_error',
          'Request validation failed',
          [{ field: 'density_g_cm3', message: 'Density must be greater than zero.', type: 'greater_than' }],
          'request-reference',
        ))
      }
      if (path === '/filaments/product-id') return Promise.resolve(filament)
      if (path === '/profiles') return Promise.resolve([profile('profile-04', '0.4', 8)])
      if (path === '/profiles/templates?include_inactive=false') return Promise.resolve([template('template-04', 'PLA', '0.4')])
      if (path === '/printers') return Promise.resolve([{ id: 'printer-id', name: 'Printer A' }])
      if (path === '/filament-colors' || path === '/vendors' || path === '/build-plates' || path === '/profiles/cura-settings/catalog') return Promise.resolve([])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit product' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save filament' }))

    const density = await screen.findByLabelText('Density (g/cm³)')
    await waitFor(() => expect(density.getAttribute('aria-invalid')).toBe('true'))
    expect(density.getAttribute('aria-describedby')).toBe('filament-product-density_g_cm3-error')
    expect(screen.getAllByText('Density must be greater than zero.').length).toBeGreaterThanOrEqual(2)
    await waitFor(() => expect(document.activeElement).toBe(density))
    expect(screen.getByText('Diagnostic reference: request-reference')).toBeTruthy()
  })
})
