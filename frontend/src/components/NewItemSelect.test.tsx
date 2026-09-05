// @vitest-environment jsdom
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { InventoryChoiceSelect } from './NewItemSelect'
import { Modal } from './Modal'

const api = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ apiFetch: api }))
afterEach(() => { cleanup(); api.mockReset() })

it('closes only the top creation dialog and retains the parent draft and focus', async () => {
  api.mockResolvedValue([])
  function Editor() {
    const [open, setOpen] = useState(true)
    return open ? <Modal title="Parent editor" onClose={() => setOpen(false)}>
      <label>Notes<input defaultValue="Unsaved draft" /></label>
      <label>Filler<InventoryChoiceSelect kind="filler" name="filler" /></label>
    </Modal> : null
  }
  render(<QueryClientProvider client={new QueryClient()}><Editor /></QueryClientProvider>)
  const select = screen.getByLabelText('Filler') as HTMLSelectElement
  await waitFor(() => expect(api).toHaveBeenCalled())
  expect(select.options[select.options.length - 1].text).toBe('New Filler')
  select.focus()
  fireEvent.change(select, { target: { value: '__filament_manager_new_item__' } })
  expect(screen.getByRole('dialog', { name: 'New Filler' })).toBeTruthy()
  expect(screen.queryByRole('dialog', { name: 'Parent editor' })).toBeNull()
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByRole('dialog', { name: 'New Filler' })).toBeNull()
  expect(screen.getByRole('dialog', { name: 'Parent editor' })).toBeTruthy()
  expect((screen.getByLabelText('Notes') as HTMLInputElement).value).toBe('Unsaved draft')
  expect(select.value).toBe('None')
  expect(document.activeElement).toBe(select)
})

it.each(['manufacturer', 'filler', 'finish', 'location'] as const)('persists and selects a new %s', async (kind) => {
  api.mockImplementation((_path: string, options?: { method?: string }) => Promise.resolve(options?.method === 'POST'
    ? { id: 'created-id', kind, name: 'New value' } : []))
  render(<QueryClientProvider client={new QueryClient()}><label>Choice<InventoryChoiceSelect kind={kind} /></label></QueryClientProvider>)
  fireEvent.change(screen.getByLabelText('Choice'), { target: { value: '__filament_manager_new_item__' } })
  const input = screen.getByRole('textbox')
  fireEvent.change(input, { target: { value: 'New value' } })
  fireEvent.submit(input.closest('form')!)
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect((screen.getByLabelText('Choice') as HTMLSelectElement).value).toBe(kind === 'manufacturer' ? 'created-id' : 'New value')
  expect(api).toHaveBeenCalledWith(kind === 'manufacturer' ? '/vendors' : kind === 'location' ? '/spool-location-choices' : '/filament-attributes', expect.objectContaining({ method: 'POST' }))
})
