// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TemplatesPage from './TemplatesPage'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({
  apiFetch: apiFetchMock,
  validationMessagesFor: () => ({}),
}))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'administrator' } }),
}))

const materialSettings = {
  chamber_temp_c: null,
  extruder_temp_c: '210',
  bed_temp_c: '60',
  initial_bed_temp_c: '65',
  flow_percent: '100',
  print_speed_mm_s: '100',
  outer_wall_speed_mm_s: null,
  inner_wall_speed_mm_s: null,
  infill_speed_mm_s: null,
  top_bottom_speed_mm_s: null,
  initial_layer_speed_mm_s: null,
  travel_speed_mm_s: null,
  support_speed_mm_s: null,
  retraction_distance_mm: null,
  retraction_speed_mm_s: null,
  retraction_prime_speed_mm_s: null,
  cooling_enabled: true,
  cooling_min_percent: '30',
  cooling_max_percent: '100',
  support_overhang_angle_deg: null,
  pressure_advance: null,
  ironing_flow_percent: null,
  ironing_speed_mm_s: null,
  ironing_line_spacing_mm: null,
  filament_density_g_cm3: '1.24',
  preferred_build_plate_surface_id: null,
  cura_extensions: {},
}

const template = {
  id: 'template-id',
  name: 'Template PLA',
  material_type: 'PLA',
  description: null,
  printer_id: 'printer-id',
  nozzle_id: 'nozzle-id',
  nozzle_diameter_mm: '0.4',
  filament_diameter_mm: '1.75000',
  active: true,
  record_version: 1,
  revisions: [{
    id: 'revision-id',
    version: 1,
    status: 'published',
    settings: materialSettings,
  }],
}

describe('TemplatesPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
    window.localStorage.clear()
  })

  it('selects a template before opening a comparison and preserves the exact pair', async () => {
    const second = { ...template, id: 'second', name: 'Template PETG', material_type: 'PETG', revisions: [{ ...template.revisions[0], id: 'second-revision', settings: { ...materialSettings, extruder_temp_c: '240' } }] }
    const third = { ...template, id: 'third', name: 'Template ASA', revisions: [{ ...template.revisions[0], id: 'third-revision' }] }
    apiFetchMock.mockImplementation((path: string) => Promise.resolve(path === '/profiles/templates' ? [template, second, third] : []))
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TemplatesPage /></QueryClientProvider>)
    const buttons = await screen.findAllByRole('button', { name: 'Compare settings' })
    fireEvent.click(buttons[0])
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(buttons[0].getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(buttons[1])
    expect(await screen.findByRole('dialog', { name: 'Compare material settings' })).toBeTruthy()
    expect(screen.getByText('Reference')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Close comparison' })).toBeNull()
    const checks = screen.getAllByRole('checkbox') as HTMLInputElement[]
    expect(checks.map((item) => item.checked)).toEqual([true, true, false])
    fireEvent.click(checks[2])
    expect(screen.getByText('Comparing 3 materials')).toBeTruthy()
  })

  it('refreshes every profile and filament cache after a direct template save', async () => {
    apiFetchMock.mockImplementation((path: string, options?: RequestInit) => {
      if (path === '/profiles/templates') return Promise.resolve([template])
      if (path === '/profiles') return Promise.resolve([])
      if (path === '/filaments') return Promise.resolve([])
      if (path === '/printers') return Promise.resolve([{ id: 'printer-id', name: 'Workshop Printer', active_nozzle_id: 'nozzle-id' }])
      if (path === '/nozzles') return Promise.resolve([{ id: 'nozzle-id', nozzle_code: 'NZ-040', printer_id: 'printer-id', diameter_mm: '0.4', material: 'Brass' }])
      if (path === '/build-plates') return Promise.resolve([])
      if (path === '/profiles/cura-settings/catalog') return Promise.resolve([])
      if (path === '/profiles/templates/template-id/settings' && options?.method === 'PUT') return Promise.resolve(template)
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const invalidation = vi.spyOn(queryClient, 'invalidateQueries')
    render(<QueryClientProvider client={queryClient}><TemplatesPage /></QueryClientProvider>)

    fireEvent.click(await screen.findByRole('button', { name: 'Edit Template PLA' }))
    expect(await screen.findByRole('dialog', { name: 'Edit Template PLA' })).toBeTruthy()
    expect((screen.getByRole('spinbutton', { name: 'Filament diameter' }) as HTMLInputElement).value).toBe('1.75')
    fireEvent.change(screen.getByLabelText('Build plate temperature (°C)'), { target: { value: '45' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save template' }))

    await screen.findByText(/Linked filament profiles inherited the changes/)
    await waitFor(() => {
      expect(invalidation).toHaveBeenCalledWith({ queryKey: ['material-templates'] })
      expect(invalidation).toHaveBeenCalledWith({ queryKey: ['profiles'] })
      expect(invalidation).toHaveBeenCalledWith({ queryKey: ['filaments'] })
      expect(invalidation).toHaveBeenCalledWith({ queryKey: ['filament'] })
    })
  })
})
