// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen } from '@testing-library/react'
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
    vi.useRealTimers()
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
    expect(screen.queryByText(/Inventory confidence/)).toBeNull()

    const printerCard = screen.getByRole('heading', { name: 'IPLT-Max' }).closest('article')
    const printerBody = screen.getByRole('region', { name: 'Current print state' }).parentElement
    const inventorySummary = screen.getByRole('region', { name: 'Inventory summary' })
    expect(printerCard).not.toBeNull()
    expect(printerBody?.classList.contains('printer-state-card__body--printing')).toBe(true)
    expect(printerCard!.compareDocumentPosition(inventorySummary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
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
    expect(screen.getByText('The dashboard will retry automatically every 10 seconds.')).toBeTruthy()
  })

  it('uses the full current-print width when no thumbnail is available', async () => {
    apiFetchMock.mockResolvedValue({
      ...dashboard,
      printer_state: { ...dashboard.printer_state, thumbnail_url: null },
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider><DashboardPage /></RouterProvider>
      </QueryClientProvider>,
    )

    const currentPrint = await screen.findByRole('region', { name: 'Current print state' })
    expect(currentPrint.classList.contains('printer-current-print--without-thumbnail')).toBe(true)
  })

  it('refreshes every ten seconds and replaces all dashboard data together', async () => {
    vi.useFakeTimers()
    apiFetchMock.mockResolvedValue({
        ...dashboard,
        total_spools: 9,
        active_spool: {
          spool_code: 'S009',
          status: 'active',
          vendor_name: 'Polymaker',
          material_type: 'PLA',
          color_name: 'Blue',
          color_mode: 'solid',
          color_hexes: ['#2457A6'],
          color_hex: '#2457A6',
          remaining_mass_effective_g: '750',
          remaining_percent: '75',
          weight_confidence: 'high',
        },
        active_plate: {
          plate_code: 'P2',
          display_name: 'Smooth PEI',
          image_url: null,
          condition: 'good',
        },
        active_plate_surface: {
          surface_code: 'P2',
          side: 'a',
          surface_material: 'PEI',
        },
        printer_state: {
          ...dashboard.printer_state,
          operational_status: 'paused',
          progress_percent: '51',
          filename: 'updated_part.gcode',
        },
      })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    })
    queryClient.setQueryData(['dashboard'], dashboard)

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider><DashboardPage /></RouterProvider>
      </QueryClientProvider>,
    )
    expect(screen.getByText('calibration_cube.gcode')).toBeTruthy()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => {
      expect(screen.getByText('updated_part.gcode')).toBeTruthy()
    })
    expect(screen.getByText('S009')).toBeTruthy()
    expect(screen.getByText('Smooth PEI')).toBeTruthy()
    expect(screen.getByText('9')).toBeTruthy()
  })
})
