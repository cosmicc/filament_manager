// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BuildPlatesPage from './BuildPlatesPage'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({ apiFetch: apiFetchMock }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'administrator-id',
      username: 'admin',
      display_name: 'Administrator',
      role: 'administrator',
      is_active: true,
      record_version: 1,
    },
  }),
}))

const printer = {
  id: 'printer-id',
  printer_code: 'printer-1',
  name: 'Workshop Printer',
  nozzle_diameter_mm: '0.4',
  active_plate_id: null,
  active_plate_surface_id: null,
  status: 'connected',
  last_seen_at: null,
  record_version: 1,
}

const plate = {
  id: 'plate-id',
  plate_code: 'P1',
  display_name: 'Build Plate P1',
  description: null,
  condition: 'good',
  status: 'active',
  preferred_materials: [],
  last_cleaned_at: null,
  notes: null,
  record_version: 1,
  surfaces: [{
    id: 'surface-id',
    build_plate_id: 'plate-id',
    side: 'a',
    surface_code: 'P1',
    klipper_mesh_profile: 'P1',
    surface_material: null,
    texture: null,
    mesh_available: true,
    last_mesh_checked_at: '2026-08-11T14:00:00Z',
    last_mesh_calibrated_at: null,
    notes: null,
    record_version: 1,
  }],
}

describe('BuildPlatesPage', () => {
  afterEach(() => {
    apiFetchMock.mockReset()
  })

  it('synchronizes Moonraker meshes and reports automatically added plates', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/build-plates') return Promise.resolve([plate])
      if (path === '/printers') return Promise.resolve([printer])
      if (path === '/build-plates/synchronize') {
        return Promise.resolve({
          printer_id: printer.id,
          discovered_codes: ['P1', 'P6'],
          created_codes: ['P6'],
          unavailable_codes: [],
          ignored_profile_count: 1,
          active_mesh_profile: 'P6',
          active_plate_code: 'P6',
          active_surface_code: 'P6',
          active_plate_changed: true,
          active_surface_changed: true,
          synchronized_at: '2026-08-11T14:01:00Z',
        })
      }
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <BuildPlatesPage />
      </QueryClientProvider>,
    )

    const synchronize = await screen.findByRole('button', { name: 'Synchronize with Moonraker' })
    fireEvent.click(synchronize)

    expect((await screen.findByText(/Added P6/)).textContent).toBe(
      'Added P6. Checked 2 P-number side meshes. Active side: P6. Ignored 1 non-plate mesh.',
    )
    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        '/build-plates/synchronize',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('selects the exact side instead of assuming the physical plate', async () => {
    const sideB = {
      ...plate.surfaces[0],
      id: 'surface-b-id',
      side: 'b',
      surface_code: 'P1b',
      klipper_mesh_profile: 'P1b',
      surface_material: 'PEX',
      texture: 'smooth',
    }
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/build-plates') return Promise.resolve([{ ...plate, surfaces: [plate.surfaces[0], sideB] }])
      if (path === '/printers') return Promise.resolve([printer])
      if (path === '/build-plates/plate-id/select') return Promise.resolve({ status: 'queued' })
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <BuildPlatesPage />
      </QueryClientProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Select P1b' }))

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith('/build-plates/plate-id/select', {
        method: 'POST',
        body: JSON.stringify({ printer_id: 'printer-id', surface_id: 'surface-b-id' }),
      })
    })
  })
})
