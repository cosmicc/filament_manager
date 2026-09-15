// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DashboardCuraSync } from './DashboardCuraSync'

const apiFetch = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ apiFetch }))

const workstation = { id: 'agent-one', display_name: 'Slicing computer', enabled: true, cura_management_enabled: true, cura_installations: [{ machines: [{ display_name: 'A completely different Cura name' }] }] }
const deployment = { id: 'deployment-one', agent_id: workstation.id, status: 'pending' }

function renderSync() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><DashboardCuraSync /></QueryClientProvider>)
  return client
}

describe('DashboardCuraSync', () => {
  afterEach(() => { cleanup(); apiFetch.mockReset() })

  it('discovers only on click and pushes a sole managed workstation without name matching', async () => {
    apiFetch.mockImplementation((path: string) => Promise.resolve(path === '/workstation-agents' ? [workstation] : [deployment]))
    const client = renderSync()
    expect(apiFetch).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Cura' }))
    expect(await screen.findByRole('status')).toHaveTextContent('App settings queued for Slicing computer')
    expect(apiFetch.mock.calls.map(([path]) => path)).toEqual(['/workstation-agents', '/workstation-agents/agent-one/sync'])
    expect(apiFetch).toHaveBeenLastCalledWith('/workstation-agents/agent-one/sync', { method: 'POST' })
    expect(client.getQueryData(['cura-deployments'])).toEqual([deployment])
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('requires an explicit choice with multiple eligible workstations and excludes ineligible ones', async () => {
    const second = { ...workstation, id: 'agent-two', display_name: 'Second computer' }
    apiFetch.mockImplementation((path: string) => Promise.resolve(path === '/workstation-agents' ? [
      workstation, second,
      { ...workstation, id: 'disabled', display_name: 'Disabled', enabled: false },
      { ...workstation, id: 'unmanaged', display_name: 'Unmanaged', cura_management_enabled: false },
      { ...workstation, id: 'missing', display_name: 'Missing installation', cura_installations: [] },
    ] : [{ ...deployment, agent_id: second.id }]))
    renderSync()
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Cura' }))
    expect(await screen.findByRole('dialog', { name: 'Sync to Cura' })).toBeTruthy()
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: /Disabled|Unmanaged|Missing installation/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Second computer' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Second computer')
    expect(apiFetch).toHaveBeenLastCalledWith('/workstation-agents/agent-two/sync', { method: 'POST' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('cancels choosing without queuing and refreshes eligibility on the next click', async () => {
    apiFetch.mockResolvedValueOnce([workstation, { ...workstation, id: 'two', display_name: 'Other computer' }]).mockResolvedValueOnce([])
    renderSync()
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Cura' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Cura' }))
    expect(await screen.findByText(/No eligible managed Cura workstation/)).toBeTruthy()
    expect(apiFetch.mock.calls.map(([path]) => path)).toEqual(['/workstation-agents', '/workstation-agents'])
  })

  it('shows discovery failures as errors rather than reporting an empty workstation list', async () => {
    apiFetch.mockRejectedValue(new Error('Workstations could not be loaded'))
    renderSync()
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Cura' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Workstations could not be loaded')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('does not report success when the server queues no deployments', async () => {
    apiFetch.mockResolvedValueOnce([workstation]).mockResolvedValueOnce([])
    renderSync()
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Cura' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No synchronization request was queued')
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('preserves server-side rejection and allows a fresh retry without claiming success', async () => {
    apiFetch.mockResolvedValueOnce([workstation]).mockRejectedValueOnce(new Error('Enable this workstation and complete takeover first')).mockResolvedValueOnce([workstation]).mockResolvedValueOnce([deployment])
    renderSync()
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Cura' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('complete takeover first')
    expect(screen.queryByRole('status')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Sync to Cura' }))
    expect(await screen.findByRole('status')).toHaveTextContent('App settings queued')
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  })
})
