// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  manufacturer: null,
  product_name: null,
  shape: 'rectangular',
  dimensions_mm: { width: '235', depth: '235', thickness: '1.2' },
  magnetic: true,
  flexible: true,
  condition: 'good',
  status: 'active',
  preferred_materials: [],
  max_bed_temp_c: '120',
  last_cleaned_at: null,
  cleaning_due_after_prints: 20,
  cleaning_due_after_days: 14,
  mesh_due_after_prints: 50,
  mesh_due_after_days: 30,
  notes: null,
  image_url: null,
  image_version: 0,
  record_version: 1,
  completed_print_count: 0,
  surfaces: [
    {
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
      completed_print_count: 0,
    },
  ],
}

describe('BuildPlatesPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
    window.localStorage.clear()
  })

  it('leaves detailed Moonraker synchronization status on Diagnostics', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/build-plates') return Promise.resolve([plate])
      if (path === '/printers') return Promise.resolve([printer])
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

    expect(await screen.findByRole('heading', { name: 'Build Plate P1' })).toBeTruthy()
    expect(screen.queryByText('Automatic Moonraker synchronization is on.')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Synchronize with Moonraker' })).toBeNull()
    expect(apiFetchMock).not.toHaveBeenCalledWith('/build-plates/synchronize', expect.anything())
  })

  it('adds the canonical Side B through the plate API', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/build-plates') return Promise.resolve([plate])
      if (path === '/printers') return Promise.resolve([printer])
      if (path === '/build-plates/plate-id/surfaces') return Promise.resolve(plate)
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

    fireEvent.click(await screen.findByRole('button', { name: 'Add Side B' }))

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith('/build-plates/plate-id/surfaces', {
        method: 'POST',
        body: JSON.stringify({}),
      })
    })
    expect(await screen.findByText('P1 Side B was added. Its mesh remains unavailable until P1b exists in Moonraker.')).toBeTruthy()
  })

  it('opens physical plate options in visible grouped sections', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/build-plates') return Promise.resolve([plate])
      if (path === '/printers') return Promise.resolve([printer])
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })

    render(<QueryClientProvider client={queryClient}><BuildPlatesPage /></QueryClientProvider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit physical plate' }))

    expect(await screen.findByRole('dialog', { name: 'Edit P1' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Identity' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Geometry' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Condition and use' })).toBeTruthy()
  })

  it('keeps physical plate actions together in a compact action row', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/build-plates') return Promise.resolve([plate])
      if (path === '/printers') return Promise.resolve([printer])
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })

    render(<QueryClientProvider client={queryClient}><BuildPlatesPage /></QueryClientProvider>)

    const editButton = await screen.findByRole('button', { name: 'Edit physical plate' })
    const actionRow = editButton.closest('.build-plate-card__actions')
    expect(actionRow).toBeTruthy()
    expect(actionRow?.classList.contains('detail-actions')).toBe(true)
    expect(actionRow?.contains(screen.getByText('Upload picture').closest('label'))).toBe(true)
    expect(actionRow?.contains(screen.getByRole('button', { name: 'Mark cleaned' }))).toBe(true)
  })

  it('opens the complete plate actions from the list presentation', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/build-plates') return Promise.resolve([plate])
      if (path === '/printers') return Promise.resolve([printer])
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })

    render(<QueryClientProvider client={queryClient}><BuildPlatesPage /></QueryClientProvider>)
    fireEvent.change(screen.getByLabelText('Build plates view'), { target: { value: 'list' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Open details' }))

    const dialog = screen.getByRole('dialog', { name: 'P1 details' })
    expect(dialog).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Edit physical plate' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Mark cleaned' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Add Side B' })).toBeTruthy()
  })

  it('shows and saves only the dimensions that match the selected shape', async () => {
    const roundPlate = {
      ...plate,
      shape: 'round',
      dimensions_mm: { width: '235', depth: '235', diameter: '240', thickness: '1.2' },
    }
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/build-plates') return Promise.resolve([roundPlate])
      if (path === '/printers') return Promise.resolve([printer])
      if (path === '/build-plates/plate-id') return Promise.resolve(roundPlate)
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })

    render(<QueryClientProvider client={queryClient}><BuildPlatesPage /></QueryClientProvider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Edit physical plate' }))

    expect(screen.getByLabelText('Diameter (mm)')).toBeTruthy()
    expect(screen.queryByLabelText('Width (mm)')).toBeNull()
    expect(screen.queryByLabelText('Depth (mm)')).toBeNull()
    expect(screen.queryByRole('option', { name: 'Other' })).toBeNull()

    fireEvent.change(screen.getByLabelText('Shape'), { target: { value: 'rectangular' } })
    expect(screen.getByLabelText('Width (mm)')).toBeTruthy()
    expect(screen.getByLabelText('Depth (mm)')).toBeTruthy()
    expect(screen.queryByLabelText('Diameter (mm)')).toBeNull()

    fireEvent.change(screen.getByLabelText('Shape'), { target: { value: 'round' } })
    fireEvent.change(screen.getByLabelText('Diameter (mm)'), { target: { value: '250' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save plate' }))

    await waitFor(() => {
      const update = apiFetchMock.mock.calls.find(([path]) => path === '/build-plates/plate-id')
      expect(update).toBeTruthy()
      const body = JSON.parse(String(update?.[1]?.body))
      expect(body.shape).toBe('round')
      expect(body.dimensions_mm).toEqual({
        width: null,
        depth: null,
        diameter: '250',
        thickness: '1.2',
      })
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
