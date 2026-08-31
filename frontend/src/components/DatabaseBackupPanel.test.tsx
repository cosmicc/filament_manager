// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from '../api/client'
import { DatabaseBackupPanel } from './DatabaseBackupPanel'

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }))

const apiFetchMock = vi.mocked(apiFetch)
const archive = {
  id: '11111111-1111-4111-8111-111111111111',
  created_at: '2026-08-28T01:00:00Z',
  application_version: '0.6.1',
  database_revision: 'a9b0c1d2e345',
  trigger: 'automatic',
  storage_kind: 'imported',
  filename: 'filament-manager-backup.zip',
  size_bytes: 2048,
  archive_sha256: 'a'.repeat(64),
  dump_sha256: 'b'.repeat(64),
}

describe('DatabaseBackupPanel', () => {
  afterEach(() => {
    cleanup()
    apiFetchMock.mockReset()
  })

  it('imports a downloaded ZIP and requires exact restore confirmation', async () => {
    apiFetchMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/diagnostics/database-backups' && !init) return Promise.resolve({
        policy: { enabled: true, interval_hours: 24, retention_count: 10, record_version: 2 },
        status: { status: 'healthy', checked_at: archive.created_at, last_success_at: archive.created_at, consecutive_failures: 0, next_retry_at: null, last_error_message: null },
        pending_restore: null,
        archives: [],
      })
      if (path === '/diagnostics/database-backups/import') return Promise.resolve(archive)
      if (path === `/diagnostics/database-backups/${archive.id}/restore-request`) return Promise.resolve({
        status: 'pending_maintenance', request_id: '22222222-2222-4222-8222-222222222222',
        backup_id: archive.id, requested_at: archive.created_at,
      })
      return Promise.reject(new Error(`Unexpected API path: ${path}`))
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><DatabaseBackupPanel isAdministrator /></QueryClientProvider>)

    const input = await screen.findByLabelText('Import backup')
    fireEvent.change(input, { target: { files: [new File(['backup'], 'backup.zip', { type: 'application/zip' })] } })

    expect(await screen.findByRole('heading', { name: 'Prepare database restore' })).toBeTruthy()
    const prepare = screen.getByRole('button', { name: 'Prepare offline restore' }) as HTMLButtonElement
    expect(prepare.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Type RESTORE exactly'), { target: { value: 'RESTORE' } })
    expect(prepare.disabled).toBe(false)
    fireEvent.click(prepare)

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith(
      `/diagnostics/database-backups/${archive.id}/restore-request`,
      { method: 'POST', body: JSON.stringify({ confirmation: 'RESTORE' }) },
    ))
  })
})
