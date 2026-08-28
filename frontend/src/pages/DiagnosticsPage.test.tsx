// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from '../api/client'
import DiagnosticsPage from './DiagnosticsPage'

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'administrator' } }),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('DiagnosticsPage', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
  })

  it('shows every stored validation check represented by the summary counts', async () => {
    const checkedAt = '2026-08-25T04:00:00Z'
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/diagnostics') return Promise.resolve({
        checked_at: checkedAt,
        checks: [{
          key: 'live.database', label: 'Current database', category: 'connection', status: 'healthy',
          detail: 'Current state is healthy.', checked_at: checkedAt,
        }],
        queue_counts: { pending: 0, running: 0, failed: 0, dead: 0 },
        job_type_counts: {},
        failure_groups: [],
        error_log: [],
      })
      if (path === '/diagnostics/version') return Promise.resolve({
        running_version: '0.5.0', latest_version: '0.4.2', status: 'ahead',
        release_url: null, detail: 'Running an unreleased testing build.',
      })
      if (path === '/diagnostics/validation-runs') return Promise.resolve([{
        id: 'validation-id', run_type: 'recovery_validation', status: 'completed',
        requested_by: 'administrator-id', started_at: checkedAt, completed_at: checkedAt,
        results: {
          summary: { healthy: 1, warning: 1, error: 1, disabled: 0 },
          checks: [
            { key: 'stored.recovery', label: 'Stored recovery check', category: 'recovery', status: 'healthy', detail: 'Healthy when recorded.', checked_at: checkedAt },
            { key: 'stored.cura', label: 'Stored Cura failure', category: 'synchronization', status: 'error', detail: 'Failed when validation ran.', checked_at: checkedAt },
            { key: 'stored.queue', label: 'Stored queue warning', category: 'worker', status: 'warning', detail: 'Retrying when validation ran.', checked_at: checkedAt },
          ],
        },
      }])
      if (path === '/diagnostics/database-backups') return Promise.resolve({
        policy: { enabled: true, interval_hours: 24, retention_count: 10, record_version: 0 },
        status: { status: 'never', checked_at: null, last_success_at: null },
        pending_restore: null,
        archives: [],
      })
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(<QueryClientProvider client={queryClient}><DiagnosticsPage /></QueryClientProvider>)

    expect(await screen.findByText('Stored recovery check')).toBeTruthy()
    expect(screen.getByText('Stored Cura failure')).toBeTruthy()
    expect(screen.getByText('Stored queue warning')).toBeTruthy()
    expect(screen.getByText(/recorded checks reflect conditions when validation ran/i)).toBeTruthy()
    expect(screen.getByText('Current database')).toBeTruthy()
    expect(await screen.findByRole('heading', { name: 'Database backups' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Recent jobs' })).toBeNull()
    expect(apiFetchMock).not.toHaveBeenCalledWith('/jobs?limit=100')
  })
})
