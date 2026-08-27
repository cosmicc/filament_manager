// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PrintHistoryPage from './PrintHistoryPage'

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ apiFetch: apiFetchMock }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'administrator' } }),
}))

const printJob = {
  id: 'print-id',
  filename: 'cube.gcode',
  source: 'live',
  status: 'completed',
  material_name: 'Workshop PLA',
  material_type: 'PLA',
  material_profile_id: 'profile-id',
  material_profile_version: 3,
  nozzle_diameter_mm: '0.4',
  state_snapshot: {
    printer: { name: 'Printer A' },
    nozzle: { code: 'NZ-040', material: 'Brass' },
    spool: { code: 'S-001' },
    filament: { product_name: 'Workshop PLA' },
    build_plate_surface: { code: 'P1' },
  },
  profile_snapshot: {},
  inspection_status: 'passed',
  inspection_policy: 'warn',
  inspection: { file_metadata: { object_height: '20', layer_count: 100, size: 1_048_576 } },
  slicer: 'Cura',
  slicer_version: '5.13',
  cura_quality_profile: 'Normal',
  machine_name: 'Printer A',
  thumbnail_url: '/api/v1/prints/print-id/thumbnail',
  thumbnail_width: 400,
  thumbnail_height: 300,
  extruder_temp_c: '215',
  initial_bed_temp_c: '65',
  bed_temp_c: '60',
  chamber_temp_c: null,
  layer_height_mm: '0.2',
  line_width_mm: '0.44',
  print_speed_mm_s: '120',
  flow_percent: '100',
  retraction_distance_mm: '0.8',
  retraction_speed_mm_s: '35',
  pressure_advance: '0.035',
  predicted_filament_length_mm: '9000',
  predicted_filament_weight_g: '27',
  actual_filament_length_mm: '8500',
  actual_filament_weight_g: '25',
  estimated_duration_seconds: '3600',
  print_duration_seconds: '3900',
  total_duration_seconds: '4000',
  actual_filament_cost: '0.75',
  predicted_filament_cost: '0.81',
  cost_currency: 'USD',
  cost_currency_conflict: false,
  cost_complete: true,
  priced_filament_weight_g: '25',
  unpriced_filament_weight_g: '0',
  timelapse_url: null,
  started_at: '2026-08-26T14:00:00Z',
  ended_at: '2026-08-26T15:05:00Z',
  segments: [{
    id: 'segment-id',
    segment_number: 1,
    source: 'print_start',
    state_snapshot: { spool: { code: 'S-001' } },
    started_at: '2026-08-26T14:00:00Z',
    ended_at: '2026-08-26T15:05:00Z',
    actual_filament_weight_g: '25',
    cost_per_gram: '0.03',
    actual_filament_cost: '0.75',
    cost_currency: 'USD',
  }],
  assessments: [],
}

describe('PrintHistoryPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
  })

  it('shows stored thumbnails, actual filament cost, useful comparisons, and segment cost', async () => {
    apiFetchMock.mockResolvedValue([printJob])
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><PrintHistoryPage /></QueryClientProvider>)

    const names = await screen.findAllByText('cube.gcode')
    expect(screen.getAllByText(/\$0\.75/).length).toBeGreaterThan(0)
    fireEvent.click(names[0])

    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(screen.getByAltText('Preview of cube.gcode')).toBeTruthy()
    expect(screen.getByText('+8% vs estimate')).toBeTruthy()
    expect(screen.getByText('-7% vs estimate')).toBeTruthy()
    expect(screen.getByText('3¢/g captured cost', { exact: false })).toBeTruthy()
  })

  it('explains why mixed-currency segment costs are not combined', async () => {
    apiFetchMock.mockResolvedValue([{
      ...printJob,
      actual_filament_cost: null,
      predicted_filament_cost: null,
      cost_currency: null,
      cost_currency_conflict: true,
      cost_complete: false,
    }])
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><PrintHistoryPage /></QueryClientProvider>)

    fireEvent.click((await screen.findAllByText('cube.gcode'))[0])

    expect(screen.getByText('Captured segment prices use different currencies and cannot be combined.')).toBeTruthy()
  })

  it('explains that the Cura inspection gate precedes the unchanged Klipper start macro', async () => {
    apiFetchMock.mockResolvedValue([{
      ...printJob,
      inspection_status: 'blocked',
      inspection_policy: 'block',
      inspection: { mismatches: [], warnings: [], printer_gate: 'not_active' },
    }])
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><PrintHistoryPage /></QueryClientProvider>)

    fireEvent.click((await screen.findAllByText('cube.gcode'))[0])

    expect(screen.getByText(/before it calls your unchanged Klipper START_PRINT macro/)).toBeTruthy()
    expect(screen.getByText(/do not add this line inside START_PRINT/)).toBeTruthy()
  })
})
