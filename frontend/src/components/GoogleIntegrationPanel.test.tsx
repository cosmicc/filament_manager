// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { apiFetch } from '../api/client'
import { GoogleIntegrationPanel } from './GoogleIntegrationPanel'

vi.mock('../api/client', () => ({ apiFetch: vi.fn(), actionableApiError: () => 'Request failed' }))
const mock = vi.mocked(apiFetch)
afterEach(() => { cleanup(); mock.mockReset() })
function show() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><GoogleIntegrationPanel /></QueryClientProvider>)
}
it('shows setup and disables connect until deployment is ready', async () => {
  mock.mockResolvedValue({ ready: false, connected: false, legacy: false, redirect_uri: 'https://example.invalid/google/callback', interval_seconds: 30 })
  show()
  expect(await screen.findByRole('heading', { name: 'One-time Google Cloud setup' })).toBeTruthy()
  expect((screen.getByRole('button', { name: 'Connect Google' }) as HTMLButtonElement).disabled).toBe(true)
})
it('queues sync and requires confirmation before disconnecting', async () => {
  mock.mockResolvedValue({ ready: true, connected: true, legacy: false, interval_seconds: 30, spreadsheet_url: 'https://docs.google.com/spreadsheets/d/test/edit' })
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Sync now' }))
  await waitFor(() => expect(mock).toHaveBeenCalledWith('/settings/google/sync', { method: 'POST' }))
  fireEvent.click(screen.getByRole('button', { name: /^Disconnect$/ }))
  expect(await screen.findByRole('dialog')).toBeTruthy()
  expect(mock).not.toHaveBeenCalledWith('/settings/google/disconnect', expect.anything())
  fireEvent.click(screen.getByRole('button', { name: 'Disconnect Google' }))
  await waitFor(() => expect(mock).toHaveBeenCalledWith('/settings/google/disconnect', { method: 'POST' }))
})
