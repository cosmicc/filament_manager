import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import { Modal } from './Modal'

type Manufacturer = { id: string; name: string; record_version: number }

/** Confirm global brand corrections while retaining physical inventory and history. */
export function ManufacturerManager({ onClose }: { onClose: () => void }) {
  const client = useQueryClient()
  const [selected, setSelected] = useState('')
  const [name, setName] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const manufacturers = useQuery({ queryKey: ['vendors'], queryFn: () => apiFetch<Manufacturer[]>('/vendors') })
  const item = manufacturers.data?.find((manufacturer) => manufacturer.id === selected)
  const rename = useMutation({
    mutationFn: () => apiFetch<Manufacturer>(`/vendors/${item!.id}`, {
      method: 'PATCH', body: JSON.stringify({ name, expected_version: item!.record_version, confirm_name: confirmation }),
    }),
    onSuccess: async (updated) => {
      client.setQueryData<Manufacturer[]>(['vendors'], (items) => items?.map((entry) => entry.id === updated.id ? updated : entry))
      setSelected(''); setName(''); setConfirmation('')
      await Promise.allSettled(['vendors', 'filaments', 'filament', 'spools', 'spool', 'dashboard'].map((key) => client.invalidateQueries({ queryKey: [key] })))
    },
  })
  return <Modal title="Manage manufacturers" onClose={() => { if (!rename.isPending) onClose() }}>
    <form className="editor-form" onSubmit={(event) => { event.preventDefault(); rename.mutate() }}>
      <p>Renaming updates this manufacturer across current and archived filaments and spools. Historical records stay unchanged. Names are saved in uppercase.</p>
      <label>Manufacturer<select aria-label="Manufacturer" value={selected} disabled={rename.isPending} required onChange={(event) => {
        setSelected(event.target.value); setName(''); setConfirmation(''); rename.reset()
      }}><option value="">Choose a manufacturer</option>{manufacturers.data?.map((entry) => <option key={entry.id} value={entry.id} disabled={entry.name === 'UNKNOWN'}>{entry.name}</option>)}</select></label>
      {item ? <>
        <label>New manufacturer name<input value={name} onChange={(event) => setName(event.target.value.toUpperCase())} required maxLength={160} disabled={rename.isPending} /></label>
        <label>Type {item.name} to confirm<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required disabled={rename.isPending} /></label>
      </> : null}
      {manufacturers.error ? <p className="form-error" role="alert">Unable to load manufacturers.</p> : null}
      {rename.error ? <p className="form-error" role="alert">{rename.error.message}</p> : null}
      <div className="form-actions"><button type="button" className="button" disabled={rename.isPending} onClick={onClose}>Close</button><button className="button button--primary" disabled={!item || !name.trim() || confirmation !== item.name || rename.isPending}>{rename.isPending ? 'Saving…' : 'Rename manufacturer'}</button></div>
    </form>
  </Modal>
}
