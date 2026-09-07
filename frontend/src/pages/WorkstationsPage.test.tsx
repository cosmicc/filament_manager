// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import WorkstationsPage from './WorkstationsPage'

const api = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ apiFetch: api }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { role: 'administrator' } }) }))
afterEach(() => { cleanup(); api.mockReset() })

const agent = {
  id: 'ws', display_name: 'Workshop', platform: 'arch_linux', hostname: 'workstation',
  agent_version: '0.7.4', enabled: true, cura_management_enabled: true,
  capabilities: {}, cura_materials: [], cura_installations: [{ installation_id: 'cura', version: '5.13', machines: [] }],
}

it('queues the complete app settings and shows confirmed sync completion', async () => {
  api.mockImplementation((path: string) => {
    if (path === '/workstation-agents') return Promise.resolve([agent])
    if (path === '/workstation-agents/ws/sync') return Promise.resolve([{ id: 'sync', status: 'pending' }])
    if (path === '/cura-deployments') return Promise.resolve([{ id: 'sync', status: 'succeeded' }])
    return Promise.reject(new Error('Unexpected request'))
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><WorkstationsPage /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Push app settings' }))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/workstation-agents/ws/sync', { method: 'POST' }))
  expect(await screen.findByText(/App settings queued for Workshop/)).toBeTruthy()
  expect(await screen.findByText(/succeeded/i, { selector: '.status-pill' })).toBeTruthy()
  expect(screen.queryByText('Map Cura profiles')).toBeNull()
})

it('disables pushes to a revoked workstation', async () => {
  api.mockResolvedValue([{ ...agent, enabled: false }])
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><WorkstationsPage /></QueryClientProvider>)
  expect((await screen.findByRole('button', { name: 'Push app settings' }) as HTMLButtonElement).disabled).toBe(true)
})
