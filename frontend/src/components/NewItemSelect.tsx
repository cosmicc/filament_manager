import { useState, type SelectHTMLAttributes } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import { Modal } from './Modal'

type Choice = { value: string; label: string }
const newItemValue = '__filament_manager_new_item__'

/** One shared convention for editable catalogs; fixed enums and filters stay selections. */
export function NewItemSelect({ itemLabel, options, onCreate, ...props }: Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> & {
  itemLabel: string
  options: Choice[]
  onCreate: () => void
}) {
  return <select {...props} onChange={(event) => {
    if (event.target.value === newItemValue) {
      // Do not change the saved selection when opening or cancelling creation.
      event.target.value = String(props.value ?? props.defaultValue ?? '')
      onCreate()
    } else props.onChange?.(event)
  }}>
    {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    <option value={newItemValue}>New {itemLabel}</option>
  </select>
}

/** Persist a simple named catalog entry, then select it without losing the parent draft. */
export function InventoryChoiceSelect({ kind, defaultValue, ...props }: Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children' | 'value' | 'onChange'> & {
  kind: 'manufacturer' | 'filler' | 'finish' | 'location'
  defaultValue?: string
}) {
  const client = useQueryClient()
  const label = kind === 'manufacturer' ? 'Manufacturer' : kind === 'filler' ? 'Filler' : kind === 'location' ? 'Location' : 'Finish'
  const fallback = kind === 'manufacturer' || kind === 'location' ? '' : kind === 'filler' ? 'None' : 'Standard'
  const [selected, setSelected] = useState((kind === 'location' ? defaultValue : defaultValue?.trim()) || fallback)
  const [creating, setCreating] = useState(false)
  const [added, setAdded] = useState<Choice[]>([])
  const isAttribute = kind === 'filler' || kind === 'finish'
  const key = kind === 'manufacturer' ? ['vendors'] : kind === 'location' ? ['spool-location-choices'] : ['filament-attributes', kind]
  const endpoint = kind === 'manufacturer' ? '/vendors' : kind === 'location' ? '/spool-location-choices' : '/filament-attributes'
  const choices = useQuery({ queryKey: key, queryFn: () => apiFetch<{ id?: string; name: string }[]>(`${endpoint}${isAttribute ? `?kind=${kind}` : ''}`) })
  const create = useMutation({
    mutationFn: (name: string) => apiFetch<{ id?: string; name: string }>(endpoint, {
      method: 'POST', body: JSON.stringify(isAttribute ? { name, kind } : { name }),
    }),
    onSuccess: async (item) => {
      const value = kind === 'manufacturer' ? item.id! : item.name
      setAdded((items) => [...items, { value, label: item.name }])
      setSelected(value)
      setCreating(false)
      // A saved choice remains successful even if a background refresh fails.
      await Promise.allSettled([client.invalidateQueries({ queryKey: key })])
    },
  })
  const options = new Map<string, string>([
    [fallback, kind === 'manufacturer' ? 'Unspecified manufacturer' : kind === 'location' ? 'Unassigned' : fallback],
    ...(choices.data ?? []).map((item): [string, string] => [kind === 'manufacturer' ? item.id! : item.name, item.name]),
    ...added.map((item): [string, string] => [item.value, item.label]),
  ])
  if (!options.has(selected)) options.set(selected, selected)
  return <>
    <NewItemSelect aria-label={label} {...props} value={selected} onChange={(event) => setSelected(event.target.value)} itemLabel={label}
      options={Array.from(options, ([value, name]) => ({ value, label: name }))}
      onCreate={() => { create.reset(); setCreating(true) }} />
    {choices.error ? <small className="form-error" role="alert">Unable to load {label.toLowerCase()} choices. Your current selection is preserved.</small> : null}
    {creating ? <Modal title={`New ${label}`} onClose={() => { if (!create.isPending) setCreating(false) }}>
      <form className="editor-form" onSubmit={(event) => {
        event.preventDefault()
        event.stopPropagation()
        create.mutate(String(new FormData(event.currentTarget).get('name') ?? '').trim())
      }}>
        <label>{label} name<input name="name" required maxLength={isAttribute ? 96 : 160} placeholder={kind === 'location' ? 'Bucket 12' : undefined} autoFocus disabled={create.isPending} /></label>
        {create.error ? <p className="form-error" role="alert">{create.error.message}</p> : null}
        <div className="form-actions"><button type="button" className="button" disabled={create.isPending} onClick={() => setCreating(false)}>Cancel</button><button className="button button--primary" disabled={create.isPending}>{create.isPending ? 'Saving…' : `Add ${label.toLowerCase()}`}</button></div>
      </form>
    </Modal> : null}
  </>
}
