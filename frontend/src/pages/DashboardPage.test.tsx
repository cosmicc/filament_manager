// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RouterProvider } from '../context/RouterContext'
import DashboardPage from './DashboardPage'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({ apiFetch: apiFetchMock }))

const dashboard = {
  total_spools: 8,
  needs_weighing: 1,
  low_spools: 1,
  empty_spools: 0,
  active_spool: null,
  active_plate: null,
  active_plate_surface: null,
  printer_state: {
    printer_name: 'IPLT-Max',
    connection_status: 'connected',
    operational_status: 'printing',
    klipper_state: 'ready',
    print_state: 'printing',
    filename: 'calibration_cube.gcode',
    progress_percent: '42.7',
    nozzle_temperature_c: '214.6',
    nozzle_target_c: '220',
    bed_temperature_c: '59.8',
    bed_target_c: '60',
    chamber_temperature_c: '37.2',
    chamber_target_c: null,
    print_job_id: 'print-id',
    thumbnail_url: '/api/v1/prints/print-id/thumbnail',
    estimated_duration_seconds: '5400',
    print_duration_seconds: '1800',
    predicted_filament_weight_g: '24',
    actual_filament_weight_g: '8.4',
    actual_filament_cost: '0.48',
    predicted_filament_cost: '1.37',
    cost_currency: 'USD',
    cost_complete: true,
    checked_at: '2026-08-25T00:30:00Z',
  },
}

describe('DashboardPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
  })

  it('shows live printer state, progress, and all available temperatures', async () => {
    apiFetchMock.mockResolvedValue(dashboard)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider><DashboardPage /></RouterProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'IPLT-Max' })).toBeTruthy()
    expect(screen.getByText('Moonraker connected · Klipper ready')).toBeTruthy()
    expect(screen.getByText('calibration_cube.gcode')).toBeTruthy()
    expect(screen.getByText('43%')).toBeTruthy()
    expect(screen.getByText('215 °C / 220 °C target')).toBeTruthy()
    expect(screen.getByText('60 °C / 60 °C target')).toBeTruthy()
    expect(screen.getByText('37 °C')).toBeTruthy()
    expect(screen.getByAltText('Preview of calibration_cube.gcode')).toBeTruthy()
    expect(screen.getByText('30 min')).toBeTruthy()
    expect(screen.getByText('8.4 g')).toBeTruthy()
    expect(screen.getByText('$0.48')).toBeTruthy()
  })

  it('explains that an unavailable connection cannot confirm printer power', async () => {
    apiFetchMock.mockResolvedValue({
      ...dashboard,
      printer_state: {
        ...dashboard.printer_state,
        connection_status: 'unavailable',
        operational_status: 'unavailable',
        klipper_state: null,
        print_state: null,
      },
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider><DashboardPage /></RouterProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Moonraker is unavailable; printer power and network state cannot be confirmed.')).toBeTruthy()
    expect(screen.getByText('The dashboard will retry automatically every 15 seconds.')).toBeTruthy()
  })
})
