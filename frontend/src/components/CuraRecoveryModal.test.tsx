// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CuraRecoverySnapshot, WorkstationAgent } from '../api/types'
import { CuraRecoveryModal } from './CuraRecoveryModal'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../api/client', () => ({ apiFetch: apiFetchMock }))

const agent: WorkstationAgent = {
  id: 'agent-id',
  agent_code: 'WS-TEST',
  display_name: 'Workshop Cura',
  hostname: 'workshop',
  platform: 'arch_linux',
  architecture: 'x86_64',
  agent_version: '0.2.5',
  enabled: true,
  cura_management_enabled: true,
  capabilities: { cura_recovery_snapshots: true },
  cura_installations: [{
    installation_id: 'cura-test',
    version: '5.13',
    channel: 'stable',
    path_hint: 'Cura 5.13',
    setting_version: 27,
    managed_library_checksum: null,
    machines: [],
  }],
  cura_materials: [],
  cura_recovery_status: 'ready',
  cura_recovery_message: null,
  last_recovery_snapshot_at: '2026-08-18T12:00:00Z',
  last_recovery_restore_at: null,
  last_seen_at: '2026-08-18T12:01:00Z',
  last_error: null,
  record_version: 1,
  created_at: '2026-08-18T11:00:00Z',
}

const snapshot: CuraRecoverySnapshot = {
  id: 'snapshot-id',
  agent_id: agent.id,
  installation_id: 'cura-test',
  cura_version: '5.13',
  setting_version: 27,
  snapshot_checksum: 'a'.repeat(64),
  file_count: 8,
  total_bytes: 12000,
  machine_count: 1,
  quality_profile_count: 3,
  plugin_count: 1,
  capture_kind: 'automatic',
  name: null,
  description: null,
  record_version: 1,
  plugins: [{
    package_id: 'MaterialSettingsPlugin',
    display_name: 'Material Settings',
    version: '4.3.1',
    enabled: true,
  }],
  captured_at: '2026-08-18T12:00:00Z',
  created_at: '2026-08-18T12:00:00Z',
}

describe('CuraRecoveryModal', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
  })

  it('reviews an exact snapshot before queueing the restore', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/workstation-agents/agent-id/cura-recovery-snapshots?include_compatible=true') return Promise.resolve([snapshot])
      if (path === '/cura-deployments') return Promise.resolve([])
      if (path === '/workstation-agents/agent-id/cura-recovery-restores') return Promise.resolve({ id: 'restore-id' })
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const onClose = vi.fn()
    const onQueued = vi.fn()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(<QueryClientProvider client={queryClient}><CuraRecoveryModal agent={agent} agents={[agent]} onClose={onClose} onQueued={onQueued} /></QueryClientProvider>)

    fireEvent.click(await screen.findByRole('button', { name: /Cura 5.13/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Review recovery' }))

    expect(await screen.findByRole('heading', { name: 'Recovery sequence' })).toBeTruthy()
    expect(screen.getByText('Material Settings')).toBeTruthy()
    expect(screen.getByText(/Account sessions, passwords, tokens/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Restore Cura setup' }))

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith('/workstation-agents/agent-id/cura-recovery-restores', {
        method: 'POST',
        body: JSON.stringify({ snapshot_id: 'snapshot-id', installation_id: 'cura-test', initialize_managed_library: false, confirmed: true }),
      })
    })
    expect(onQueued).toHaveBeenCalledWith(expect.stringContaining('Cura 5.13 recovery was queued'))
    expect(onClose).toHaveBeenCalled()
  })

  it('shows saved configurations before recent backup requests', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/workstation-agents/agent-id/cura-recovery-snapshots?include_compatible=true') return Promise.resolve([snapshot])
      if (path === '/cura-deployments') return Promise.resolve([{
        id: 'deployment-id',
        agent_id: agent.id,
        operation: 'recovery_capture',
        status: 'failed',
        attempts: 1,
        last_error_message: 'Backup did not complete safely.',
        created_at: '2026-08-18T12:02:00Z',
      }])
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(<QueryClientProvider client={queryClient}><CuraRecoveryModal agent={agent} agents={[agent]} onClose={vi.fn()} onQueued={vi.fn()} /></QueryClientProvider>)

    const saved = await screen.findByRole('heading', { name: 'Saved Cura configurations' })
    const requests = await screen.findByRole('heading', { name: 'Recent backup requests' })
    expect(saved.compareDocumentPosition(requests) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
