// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BuildPlate } from '../api/types'
import { apiFetch } from '../api/client'
import { PlateCompatibility, PlateRatingEditor } from './PlateCompatibility'

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
const plates = [
  { id: 'p1', plate_code: 'P1', display_name: 'Smooth', status: 'active', surfaces: [{ id: 's1' }, { id: 's1b' }] },
  { id: 'p2', plate_code: 'P2', display_name: 'Textured', status: 'active', surfaces: [{ id: 's2' }] },
] as BuildPlate[]

function wrap(content: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{content}</QueryClientProvider>)
}

describe('whole-plate ratings', () => {
  it('shows one star control per whole plate and persists sparse overrides/revert', async () => {
    let saved: Record<string, number> = {}
    vi.mocked(apiFetch).mockImplementation(async (_path, options) => {
      if (options?.method === 'PUT') saved = JSON.parse(String(options.body)).ratings
      return { record_version: 1, ratings: saved } as never
    })
    wrap(<PlateRatingEditor filamentId="filament" plates={plates} inherited={{ p1: 4, p2: 5 }} />)
    await waitFor(() => expect((screen.getByRole('button', { name: 'Rate P1 3 stars' }) as HTMLButtonElement).disabled).toBe(false))
    expect(screen.getAllByRole('group')).toHaveLength(2)
    expect(screen.getAllByText('Inherited')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Rate P1 3 stars' }))
    await waitFor(() => expect(saved).toEqual({ p1: 3 }))
    await screen.findByText('Customized')
    fireEvent.click(screen.getByRole('button', { name: 'Revert to Template for P1' }))
    await waitFor(() => expect(saved).toEqual({}))
    await waitFor(() => expect(screen.getAllByText('Inherited')).toHaveLength(2))
  })

  it.each([0, 3, 5])('warns correctly for active rating %s, never warning on a best-rating tie', async (active) => {
    vi.mocked(apiFetch).mockImplementation(async (path) => path === '/build-plates' ? plates as never : [{
      printer_id: 'printer', printer_name: 'Workshop', active_plate_id: 'p1', template_id: 'template',
      template_name: 'Template PLA', ratings: { p1: active, p2: 5 }, inherited_ratings: { p1: active, p2: 5 }, overrides: {},
    }] as never)
    wrap(<PlateCompatibility filamentId="filament" />)
    await screen.findByText(/Recommended:/)
    if (active === 0) expect(screen.getByText(/Do NOT use/)).toBeTruthy()
    else if (active === 3) expect(screen.getByText('A better-rated build plate is available.')).toBeTruthy()
    else expect(screen.queryByRole('alert')).toBeNull()
  })
})
