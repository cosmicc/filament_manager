// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MaterialTypeManager, MaterialTypeSelect } from './MaterialTypeSelect'

const fetchMock = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ apiFetch: fetchMock }))
const choice = { id: 'type-id', name: 'ASA', record_version: 3 }

function client() { return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }) }
afterEach(() => { cleanup(); fetchMock.mockReset() })

describe('Material type controls', () => {
  it('preserves the parent draft on cancel, creates a durable choice and selects it', async () => {
    fetchMock.mockImplementation((_path: string, options?: RequestInit) => Promise.resolve(options?.method === 'POST' ? { id: 'new', name: 'ASA-CF', record_version: 1 } : [choice]))
    const submit = vi.fn()
    render(<QueryClientProvider client={client()}><form onSubmit={(event) => { event.preventDefault(); submit() }}><label>Draft description<input defaultValue="Keep these settings" /></label><label>Material type<MaterialTypeSelect name="material_type" defaultValue="ASA" /></label></form></QueryClientProvider>)
    const select = screen.getByLabelText('Material type')
    await screen.findByRole('option', { name: 'ASA' })
    fireEvent.change(select, { target: { value: '__filament_manager_new_item__' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect((select as HTMLSelectElement).value).toBe('ASA')
    expect((screen.getByLabelText('Draft description') as HTMLInputElement).value).toBe('Keep these settings')
    fireEvent.change(select, { target: { value: '__filament_manager_new_item__' } })
    fireEvent.change(screen.getByLabelText('Material type name'), { target: { value: 'ASA-CF' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add material type' }))
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe('ASA-CF'))
    expect(submit).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledWith('/profiles/material-types', expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: 'ASA-CF' }) }))
  })

  it('submits an exact confirmed global rename and invalidates affected catalogs', async () => {
    fetchMock.mockImplementation((_path: string, options?: RequestInit) => Promise.resolve(options?.method === 'PUT' ? { ...choice, name: 'ASA-CF', record_version: 4 } : [choice]))
    const queryClient = client()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    render(<QueryClientProvider client={queryClient}><MaterialTypeManager onClose={() => undefined} /></QueryClientProvider>)
    fireEvent.change(await screen.findByLabelText('Managed material type'), { target: { value: 'ASA' } })
    fireEvent.change(screen.getByLabelText('New name'), { target: { value: 'ASA-CF' } })
    fireEvent.change(screen.getByLabelText('Type ASA to confirm'), { target: { value: 'ASA' } })
    fireEvent.click(screen.getByRole('button', { name: 'Rename material type everywhere' }))
    await screen.findByText(/Material type renamed to ASA-CF/)
    expect(fetchMock).toHaveBeenCalledWith('/profiles/material-types/type-id', expect.objectContaining({ method: 'PUT', body: JSON.stringify({ name: 'ASA-CF', confirmation_name: 'ASA', expected_version: 3 }) }))
    for (const key of ['material-types', 'material-templates', 'filaments', 'spools', 'profiles']) expect(invalidate).toHaveBeenCalledWith({ queryKey: [key] })
  })

  it('keeps rename failures inside the dialog without claiming success', async () => {
    fetchMock.mockImplementation((_path: string, options?: RequestInit) => options?.method === 'PUT' ? Promise.reject(new Error('That material type already exists')) : Promise.resolve([choice]))
    render(<QueryClientProvider client={client()}><MaterialTypeManager onClose={() => undefined} /></QueryClientProvider>)
    fireEvent.change(await screen.findByLabelText('Managed material type'), { target: { value: 'ASA' } })
    fireEvent.change(screen.getByLabelText('Type ASA to confirm'), { target: { value: 'ASA' } })
    fireEvent.click(screen.getByRole('button', { name: 'Rename material type everywhere' }))
    expect((await screen.findByRole('alert')).textContent).toContain('already exists')
    expect(screen.queryByText(/Material type renamed to/)).toBeNull()
  })
})
