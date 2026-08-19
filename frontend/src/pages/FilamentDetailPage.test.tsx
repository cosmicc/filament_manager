// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../context/RouterContext'
import FilamentDetailPage from './FilamentDetailPage'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({
  apiFetch: apiFetchMock,
  validationMessagesFor: vi.fn(() => ({})),
}))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'operator' } }),
}))

const settings = {
  chamber_temp_c: null,
  extruder_temp_c: '215',
  bed_temp_c: '60',
  flow_percent: '100',
  print_speed_mm_s: '60',
  outer_wall_speed_mm_s: '30',
  inner_wall_speed_mm_s: '60',
  infill_speed_mm_s: '60',
  top_bottom_speed_mm_s: '30',
  initial_layer_speed_mm_s: '20',
  travel_speed_mm_s: '150',
  support_speed_mm_s: '50',
  retraction_distance_mm: '0.8',
  retraction_speed_mm_s: '35',
  cooling_enabled: true,
  cooling_min_percent: '20',
  cooling_max_percent: '100',
  support_overhang_angle_deg: '50',
  tree_max_branch_angle_deg: null,
  pressure_advance: '0.04',
  filament_density_g_cm3: '1.24',
  preferred_build_plate_surface_id: null,
  cura_extensions: {},
}

function template(id: string, name: string, revisionId: string) {
  return {
    id,
    name,
    material_type: 'PLA',
    description: null,
    printer_id: 'printer-id',
    nozzle_diameter_mm: '0.40000',
    filament_diameter_mm: '1.75000',
    source_workstation_agent_id: null,
    source_cura_material_id: null,
    active: true,
    record_version: 1,
    created_at: '2026-08-18T00:00:00Z',
    updated_at: '2026-08-18T00:00:00Z',
    revisions: [{
      id: revisionId,
      material_template_id: id,
      version: 2,
      status: 'published',
      settings,
      checksum: null,
      published_at: '2026-08-18T00:00:00Z',
      record_version: 1,
      created_at: '2026-08-18T00:00:00Z',
    }],
  }
}

describe('FilamentDetailPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
    window.history.replaceState(null, '', '/')
  })

  it('selects the current template snapshot and lists other compatible templates', async () => {
    window.history.replaceState(null, '', '/filaments/product-id')
    const filament = {
      id: 'product-id', vendor_id: null, vendor_name: null, material_type: 'PLA', filler: null,
      finish: null, color_name: 'Blue', color_hex: '2244AA', color_mode: 'solid',
      color_hexes: ['2244AA'], product_name: 'Workshop PLA', diameter_mm: '1.75',
      tolerance_mm: null, density_g_cm3: '1.24', nominal_net_mass_g: '1000', notes: null,
      material_template_revision_id: 'superseded-revision', archived: false, color_editable: true,
      record_version: 1,
    }
    const profile = {
      ...settings,
      id: 'profile-id', filament_product_id: 'product-id', printer_id: 'printer-id',
      nozzle_diameter_mm: '0.4', version: 3, status: 'published', cura_settings: {},
      published_at: '2026-08-18T00:00:00Z', checksum: null, record_version: 1,
      base_template_revision_id: 'superseded-revision', setting_overrides: {}, override_keys: [],
      override_count: 0, inheritance_status: 'inherited', base_template_id: 'current-template',
      base_template_name: 'Template PLA', base_template_version: 1, base_template_settings: settings,
      latest_template_revision_id: 'current-revision', latest_template_version: 2,
      template_update_changes: [], source_workstation_agent_id: null, source_cura_material_id: null,
    }
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/filaments/product-id') return Promise.resolve(filament)
      if (path === '/filament-colors' || path === '/vendors' || path === '/printers' || path === '/build-plates' || path === '/profiles/cura-settings/catalog') return Promise.resolve([])
      if (path === '/profiles') return Promise.resolve([profile])
      if (path === '/profiles/templates?include_inactive=false') return Promise.resolve([
        template('alternate-template', 'Template PLA Alternate', 'alternate-revision'),
        template('current-template', 'Template PLA', 'current-revision'),
      ])
      return Promise.reject(new Error(`Unexpected API request: ${path}`))
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider><FilamentDetailPage /></RouterProvider>
      </QueryClientProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const selector = await screen.findByLabelText(/Linked material template/) as HTMLSelectElement
    expect(selector.value).toBe('current-revision')
    expect(Array.from(selector.options).map((option) => option.text)).toEqual([
      'Select a template',
      'Template PLA · 0.4 mm · Current',
      'Template PLA Alternate · 0.4 mm',
    ])
  })
})
