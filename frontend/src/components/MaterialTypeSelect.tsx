import { useState, type SelectHTMLAttributes } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import { Modal } from './Modal'
import { NewItemSelect } from './NewItemSelect'

export interface MaterialTypeChoice { id: string; name: string; record_version: number }
export const materialTypeQueryKey = ['material-types']
export const materialTypeEndpoint = '/profiles/material-types'

/** Durable choices use the same catalog in imports, template creation, and management. */
export function useMaterialTypes() {
  return useQuery({ queryKey: materialTypeQueryKey, queryFn: () => apiFetch<MaterialTypeChoice[]>(materialTypeEndpoint) })
}

/** Create a family in a child dialog without discarding the originating template draft. */
export function MaterialTypeSelect({ defaultValue = '', value, onSelectionChange, ...props }: Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children' | 'onChange'> & { onSelectionChange?: (value: string) => void }) {
  const client = useQueryClient()
  const choices = useMaterialTypes()
  const [selected, setSelected] = useState(String(defaultValue))
  const [creating, setCreating] = useState(false)
  const effective = value === undefined ? selected : String(value)
  const create = useMutation({
    mutationFn: (name: string) => apiFetch<MaterialTypeChoice>(materialTypeEndpoint, { method: 'POST', body: JSON.stringify({ name }) }),
    onSuccess: (item) => {
      client.setQueryData<MaterialTypeChoice[]>(materialTypeQueryKey, (items) => [...(items ?? []).filter((value) => value.id !== item.id), item])
      setSelected(item.name)
      onSelectionChange?.(item.name)
      setCreating(false)
      void Promise.allSettled([client.invalidateQueries({ queryKey: materialTypeQueryKey })])
    },
  })
  const names = Array.from(new Set([...(choices.data ?? []).map((item) => item.name), ...(effective ? [effective] : [])])).sort((a, b) => a.localeCompare(b))
  return <>
    <NewItemSelect {...props} value={effective} itemLabel="Material Type" options={[{ value: '', label: 'Select material type' }, ...names.map((name) => ({ value: name, label: name }))]} onChange={(event) => { setSelected(event.target.value); onSelectionChange?.(event.target.value) }} onCreate={() => { create.reset(); setCreating(true) }} />
    {choices.isError ? <small className="form-error" role="alert">Unable to load material types. Your current selection is preserved.</small> : null}
    {creating ? <Modal title="New Material Type" onClose={() => { if (!create.isPending) setCreating(false) }}>
      <form className="editor-form" onSubmit={(event) => { event.preventDefault(); event.stopPropagation(); create.mutate(String(new FormData(event.currentTarget).get('name') ?? '').trim()) }}>
        <label>Material type name<input name="name" maxLength={48} required autoFocus disabled={create.isPending} placeholder="ASA-CF" /></label>
        <p className="field-help">Adds a selectable type. Template settings are configured separately.</p>
        {create.error ? <p className="form-error" role="alert">{create.error.message}</p> : null}
        <div className="form-actions"><button type="button" className="button" disabled={create.isPending} onClick={() => setCreating(false)}>Cancel</button><button className="button button--primary" disabled={create.isPending}>{create.isPending ? 'Adding…' : 'Add material type'}</button></div>
      </form>
    </Modal> : null}
  </>
}

/** Confirm global renames explicitly; successful commits refresh every affected live catalog. */
export function MaterialTypeManager({ onClose }: { onClose: () => void }) {
  const choices = useMaterialTypes()
  const client = useQueryClient()
  const [selectedName, setSelectedName] = useState('')
  const target = choices.data?.find((item) => item.name === selectedName) ?? null
  const [message, setMessage] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteName, setDeleteName] = useState('')
  const remove = useMutation({
    mutationFn: (item: MaterialTypeChoice) => apiFetch<MaterialTypeChoice>(`${materialTypeEndpoint}/${item.id}`, {
      method: 'DELETE', body: JSON.stringify({ expected_version: item.record_version, confirmation_name: deleteName }),
    }),
    onSuccess: (item) => {
      // Keep committed deletion visible even if a later cache refresh fails.
      client.setQueryData<MaterialTypeChoice[]>(materialTypeQueryKey, (items) => items?.filter((value) => value.id !== item.id))
      setSelectedName('')
      setConfirmDelete(false)
      setDeleteName('')
      setMessage(`${item.name} was deleted from material type choices. Existing filament records and history were preserved.`)
      void Promise.allSettled([client.invalidateQueries({ queryKey: materialTypeQueryKey })])
    },
  })
  const rename = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form)
      return apiFetch<MaterialTypeChoice>(`${materialTypeEndpoint}/${target!.id}`, { method: 'PUT', body: JSON.stringify({ name: String(data.get('name')).trim(), confirmation_name: String(data.get('confirmation_name')), expected_version: target!.record_version }) })
    },
    onSuccess: (item) => {
      setSelectedName('')
      setMessage(`Material type renamed to ${item.name}. Current templates and filaments were updated; synchronization was queued.`)
      void Promise.allSettled(['material-types', 'material-templates', 'profiles', 'filaments', 'filament', 'spools', 'dashboard', 'workstation-agents'].map((key) => client.invalidateQueries({ queryKey: [key] })))
    },
  })
  return <Modal title="Manage material types" onClose={onClose}>
    <div className="editor-form">
      <p>Renaming updates all templates and filaments using the type, including archived inventory. Settings, spool codes, and historical print records are preserved.</p>
      {message ? <p className="deployment-note" role="status">{message}</p> : null}
      {choices.isError ? <p className="form-error" role="alert">Unable to load material types.</p> : choices.isLoading ? <p>Loading material types…</p> : <label>Material type<MaterialTypeSelect aria-label="Managed material type" disabled={rename.isPending || remove.isPending} value={target?.name ?? ''} onSelectionChange={(name) => { setSelectedName(name); setConfirmDelete(false); setDeleteName(''); setMessage(''); rename.reset(); remove.reset() }} /></label>}
      {target && !confirmDelete ? <form className="editor-form" key={target.id} onSubmit={(event) => { event.preventDefault(); rename.mutate(event.currentTarget) }}>
        <label>New name<input name="name" defaultValue={target.name} maxLength={48} required disabled={rename.isPending} /></label>
        <label>Type {target.name} to confirm<input name="confirmation_name" required maxLength={48} autoComplete="off" disabled={rename.isPending} /></label>
        {rename.error ? <p className="form-error" role="alert">{rename.error.message}</p> : null}
        <div className="form-actions"><button type="button" className="button button--danger" disabled={rename.isPending} onClick={() => { setConfirmDelete(true); setDeleteName(''); remove.reset() }}>Delete material type</button><button className="button button--primary" disabled={rename.isPending}>{rename.isPending ? 'Renaming…' : 'Rename material type everywhere'}</button></div>
      </form> : null}
      {target && confirmDelete ? <form className="editor-form" onSubmit={(event) => { event.preventDefault(); remove.mutate(target) }}>
        <p>Delete {target.name} from material type choices? Active templates prevent deletion. Existing filament records and historical labels are preserved.</p>
        <label>Type {target.name} to delete<input value={deleteName} onChange={(event) => setDeleteName(event.target.value)} maxLength={48} required autoComplete="off" autoFocus disabled={remove.isPending} /></label>
        {remove.error ? <p className="form-error" role="alert">{remove.error.message}</p> : null}
        <div className="form-actions"><button type="button" className="button" disabled={remove.isPending} onClick={() => { setConfirmDelete(false); setDeleteName(''); remove.reset() }}>Cancel deletion</button><button className="button button--danger" disabled={remove.isPending || deleteName !== target.name}>{remove.isPending ? 'Deleting…' : 'Confirm deletion'}</button></div>
      </form> : null}
    </div>
  </Modal>
}
