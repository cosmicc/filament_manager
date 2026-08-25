import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Pencil, Plus, Save, Search, Unplug, Wrench } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import type { Nozzle, NozzleLifecycleEvent, Printer } from '../api/types'
import { CollectionViewSelector } from '../components/CollectionViewSelector'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { useCollectionView } from '../hooks/useCollectionView'
import { compactNumber, dateTime, inputNumber, titleCase } from '../lib/format'

function optional(data: FormData, key: string) {
  return String(data.get(key) ?? '').trim() || null
}

function NozzleEditor({ nozzle, printers, pending, error, onClose, onSave }: {
  nozzle: Nozzle | null
  printers: Printer[]
  pending: boolean
  error: string
  onClose: () => void
  onSave: (values: Record<string, unknown>) => void
}) {
  const formId = nozzle ? `edit-nozzle-${nozzle.id}` : 'create-nozzle'
  return <Modal
    title={nozzle ? `Edit ${nozzle.nozzle_code}` : 'Add physical nozzle'}
    description="Track the exact physical nozzle so completed prints remain tied to the hardware that produced them."
    onClose={onClose}
    footer={<><button className="button" onClick={onClose}>Cancel</button><button className="button button--primary" form={formId} disabled={pending}><Save size={17} />{pending ? 'Saving…' : 'Save nozzle'}</button></>}
  >
    <form id={formId} className="editor-form" onSubmit={(event) => {
      event.preventDefault()
      const data = new FormData(event.currentTarget)
      onSave({
        ...(nozzle ? { expected_version: nozzle.record_version } : {}),
        ...(!nozzle ? { printer_id: String(data.get('printer_id') ?? '') } : {}),
        nozzle_code: String(data.get('nozzle_code') ?? '').trim(),
        diameter_mm: String(data.get('diameter_mm') ?? ''),
        material: String(data.get('material') ?? '').trim(),
        manufacturer: optional(data, 'manufacturer'),
        product_name: optional(data, 'product_name'),
        coating: optional(data, 'coating'),
        purchase_date: optional(data, 'purchase_date'),
        notes: optional(data, 'notes'),
      })
    }}>
      <EditorSection title="Identity" description="Use a durable label attached to or stored with this nozzle.">
        <div className="form-grid">
          {nozzle ? <label>Printer<input value={printers.find((printer) => printer.id === nozzle.printer_id)?.name ?? 'Unknown printer'} disabled /></label> : <label>Printer<select name="printer_id" required>{printers.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label>}
          <label>Nozzle code<input name="nozzle_code" defaultValue={nozzle?.nozzle_code ?? ''} required maxLength={64} pattern={'[A-Za-z0-9][A-Za-z0-9._\\-]*'} autoFocus /></label>
          <label>Diameter (mm)<input name="diameter_mm" defaultValue={inputNumber(nozzle?.diameter_mm, 1)} required type="number" min="0.1" max="10" step="0.1" /></label>
          <label>Material<input name="material" defaultValue={nozzle?.material ?? ''} required maxLength={96} placeholder="Brass, hardened steel…" /></label>
          <label>Coating<input name="coating" defaultValue={nozzle?.coating ?? ''} maxLength={96} placeholder="Nickel plated, DLC…" /></label>
        </div>
      </EditorSection>
      <EditorSection title="Product details" description="Optional purchasing and manufacturer details make replacements easier.">
        <div className="form-grid">
          <label>Manufacturer<input name="manufacturer" defaultValue={nozzle?.manufacturer ?? ''} maxLength={160} /></label>
          <label>Product or model<input name="product_name" defaultValue={nozzle?.product_name ?? ''} maxLength={160} /></label>
          <label>Purchase date<input name="purchase_date" type="date" defaultValue={nozzle?.purchase_date ?? ''} /></label>
          <label className="form-grid__wide">Notes<textarea name="notes" defaultValue={nozzle?.notes ?? ''} maxLength={4000} rows={3} /></label>
        </div>
      </EditorSection>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </form>
  </Modal>
}

export default function NozzlesPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const [editing, setEditing] = useState<Nozzle | 'new' | null>(null)
  const [selected, setSelected] = useState<Nozzle | null>(null)
  const [detailsNozzle, setDetailsNozzle] = useState<Nozzle | null>(null)
  const [search, setSearch] = useState('')
  const [view, setView] = useCollectionView('nozzles', 'cards')
  const [message, setMessage] = useState('')
  const nozzles = useQuery({ queryKey: ['nozzles'], queryFn: () => apiFetch<Nozzle[]>('/nozzles?include_retired=true') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const events = useQuery({ queryKey: ['nozzle-events', selected?.id], queryFn: () => apiFetch<NozzleLifecycleEvent[]>(`/nozzles/${selected?.id}/events`), enabled: Boolean(selected) })
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['nozzles'] }),
      client.invalidateQueries({ queryKey: ['printers'] }),
      client.invalidateQueries({ queryKey: ['nozzle-events'] }),
    ])
  }
  const save = useMutation({
    mutationFn: ({ nozzle, values }: { nozzle: Nozzle | null; values: Record<string, unknown> }) => apiFetch<Nozzle>(nozzle ? `/nozzles/${nozzle.id}` : '/nozzles', { method: nozzle ? 'PATCH' : 'POST', body: JSON.stringify(values) }),
    onSuccess: async () => { setEditing(null); setMessage('Nozzle record saved.'); await refresh() },
  })
  const install = useMutation({
    mutationFn: ({ nozzle, printerId }: { nozzle: Nozzle; printerId: string }) => apiFetch<Nozzle>(`/nozzles/${nozzle.id}/install`, { method: 'POST', body: JSON.stringify({ printer_id: printerId }) }),
    onSuccess: async () => { setMessage('Physical nozzle installation recorded.'); await refresh() },
  })
  const remove = useMutation({
    mutationFn: (nozzle: Nozzle) => apiFetch<Nozzle>(`/nozzles/${nozzle.id}/remove`, { method: 'POST', body: JSON.stringify({ printer_id: nozzle.installed_printer_id }) }),
    onSuccess: async () => { setMessage('Physical nozzle removal recorded.'); await refresh() },
  })
  const retire = useMutation({
    mutationFn: (nozzle: Nozzle) => apiFetch<Nozzle>(`/nozzles/${nozzle.id}`, { method: 'PATCH', body: JSON.stringify({ expected_version: nozzle.record_version, retired: nozzle.status !== 'retired' }) }),
    onSuccess: async () => { setMessage('Nozzle lifecycle updated.'); await refresh() },
  })
  const canEdit = user?.role !== 'viewer'
  const visibleNozzles = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    if (!needle) return nozzles.data ?? []
    return (nozzles.data ?? []).filter((nozzle) => [nozzle.nozzle_code, nozzle.diameter_mm, nozzle.material, nozzle.manufacturer, nozzle.product_name, nozzle.coating, nozzle.status].filter(Boolean).join(' ').toLocaleLowerCase().includes(needle))
  }, [nozzles.data, search])
  useEffect(() => {
    if (!detailsNozzle) return
    const current = nozzles.data?.find((nozzle) => nozzle.id === detailsNozzle.id)
    if (current && current !== detailsNozzle) setDetailsNozzle(current)
  }, [detailsNozzle, nozzles.data])

  const renderDetailedNozzle = (nozzle: Nozzle) => {
    const installedPrinter = printers.data?.find((printer) => printer.id === nozzle.installed_printer_id)
    const assignedPrinter = printers.data?.find((printer) => printer.id === nozzle.printer_id)
    return <article className={`integration-card nozzle-card nozzle-card--detailed${nozzle.installed_printer_id ? ' nozzle-card--installed' : ''}`} key={nozzle.id}>
      <span className="integration-card__icon"><Wrench size={23} /></span>
      <div><p className="eyebrow">{nozzle.nozzle_code}</p><h2>{compactNumber(nozzle.diameter_mm, 1)} mm {nozzle.material}</h2><p>{[nozzle.manufacturer, nozzle.product_name, nozzle.coating].filter(Boolean).join(' · ') || 'No product details recorded'}</p></div>
      <StatusPill status={nozzle.status} />
      <dl className="definition-list definition-list--compact nozzle-card__facts">
        <div><dt>Printer</dt><dd>{assignedPrinter?.name ?? 'Unknown printer'}</dd></div>
        <div><dt>Installed on</dt><dd>{installedPrinter?.name ?? 'Not installed'}</dd></div>
        <div><dt>Completed prints</dt><dd>{nozzle.completed_print_count.toLocaleString()}</dd></div>
        <div><dt>Recorded filament</dt><dd>{Number(nozzle.completed_filament_weight_g).toLocaleString(undefined, { maximumFractionDigits: 1 })} g</dd></div>
        <div><dt>Installed</dt><dd>{dateTime(nozzle.installed_at)}</dd></div>
      </dl>
      <div className="detail-actions">
        <button className="button" onClick={() => { setDetailsNozzle(null); setSelected(nozzle) }}><History size={16} /> History</button>
        {canEdit ? <button className="button" onClick={() => { setDetailsNozzle(null); setEditing(nozzle) }}><Pencil size={16} /> Edit</button> : null}
      </div>
      {canEdit && nozzle.status !== 'retired' ? <div className="inline-action-group">
        {nozzle.installed_printer_id ? <button className="button" disabled={remove.isPending} onClick={() => remove.mutate(nozzle)}><Unplug size={16} /> Record removal</button> : <button className="button button--primary" disabled={install.isPending} onClick={() => install.mutate({ nozzle, printerId: nozzle.printer_id })}>Install on {assignedPrinter?.name ?? 'assigned printer'}</button>}
      </div> : null}
      {canEdit && !nozzle.installed_printer_id ? <button className="text-button" disabled={retire.isPending} onClick={() => retire.mutate(nozzle)}>{nozzle.status === 'retired' ? 'Reactivate nozzle' : 'Retire nozzle'}</button> : null}
    </article>
  }

  return <div>
    <PageHeader eyebrow="Physical tooling" title="Nozzles" description="Track each physical nozzle, its installation history, and completed-print use." actions={canEdit ? <button className="button button--primary" onClick={() => { setEditing('new'); setMessage('') }}><Plus size={17} /> Add nozzle</button> : undefined} />
    {message ? <div className="deployment-note" role="status">{message}</div> : null}
    {nozzles.error ? <p className="form-error">{nozzles.error.message}</p> : null}
    <section className="toolbar"><label className="search-field"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search code, size, material, or product" aria-label="Search nozzles" /></label><CollectionViewSelector label="Nozzles" value={view} onChange={setView} /><span className="toolbar__summary">{visibleNozzles.length} nozzles</span></section>
    {nozzles.isLoading ? <LoadingState /> : !nozzles.data?.length ? <EmptyState icon={Wrench} title="No physical nozzles recorded" description="Add the nozzle currently installed in the printer, then record its installation to begin exact print-use tracking." action={canEdit ? <button className="button button--primary" onClick={() => setEditing('new')}><Plus size={17} /> Add first nozzle</button> : undefined} /> : !visibleNozzles.length ? <EmptyState icon={Search} title="No nozzles match" description="Adjust the search to see another physical nozzle." /> : view === 'list' ? <div className="table-card collection-table"><table><thead><tr><th>Nozzle</th><th>Printer</th><th>Product</th><th>Status</th><th>Prints</th><th>Filament</th></tr></thead><tbody>{visibleNozzles.map((nozzle) => { const assignedPrinter = printers.data?.find((printer) => printer.id === nozzle.printer_id); return <tr key={nozzle.id} tabIndex={0} onClick={() => setDetailsNozzle(nozzle)} onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && setDetailsNozzle(nozzle)}><td><strong>{nozzle.nozzle_code}</strong><small className="table-subtext">{compactNumber(nozzle.diameter_mm, 1)} mm {nozzle.material}</small></td><td><strong>{assignedPrinter?.name ?? 'Unknown printer'}</strong><small className="table-subtext">{nozzle.installed_printer_id ? 'Currently installed' : 'Assigned printer'}</small></td><td>{[nozzle.manufacturer, nozzle.product_name, nozzle.coating].filter(Boolean).join(' · ') || 'Not recorded'}</td><td><StatusPill status={nozzle.status} /></td><td>{nozzle.completed_print_count.toLocaleString()}</td><td>{Number(nozzle.completed_filament_weight_g).toLocaleString(undefined, { maximumFractionDigits: 1 })} g</td></tr> })}</tbody></table></div> : view === 'detailed' ? <section className="collection-grid collection-grid--detailed">{visibleNozzles.map(renderDetailedNozzle)}</section> : <section className="collection-grid collection-grid--cards">{visibleNozzles.map((nozzle) => { const assignedPrinter = printers.data?.find((printer) => printer.id === nozzle.printer_id); return <button className={`collection-card collection-card--button${nozzle.installed_printer_id ? ' nozzle-card--installed' : ''}`} key={nozzle.id} onClick={() => setDetailsNozzle(nozzle)}><header className="collection-card__header"><span className="integration-card__icon"><Wrench size={23} /></span><StatusPill status={nozzle.status} /></header><div className="collection-card__body"><p className="eyebrow">{nozzle.nozzle_code}</p><h2>{compactNumber(nozzle.diameter_mm, 1)} mm {nozzle.material}</h2><p>{assignedPrinter?.name ?? 'Unknown printer'}</p></div><dl className="catalog-meta"><div><dt>Installation</dt><dd>{nozzle.installed_printer_id ? 'Currently installed' : 'Not installed'}</dd></div><div><dt>Completed prints</dt><dd>{nozzle.completed_print_count.toLocaleString()}</dd></div><div><dt>Recorded filament</dt><dd>{Number(nozzle.completed_filament_weight_g).toLocaleString(undefined, { maximumFractionDigits: 1 })} g</dd></div><div><dt>Product</dt><dd>{[nozzle.manufacturer, nozzle.product_name].filter(Boolean).join(' · ') || 'Not recorded'}</dd></div></dl></button>})}</section>}
    {[save.error, install.error, remove.error, retire.error].find(Boolean) ? <p className="form-error" role="alert">{[save.error, install.error, remove.error, retire.error].find(Boolean)?.message}</p> : null}
    {editing ? <NozzleEditor nozzle={editing === 'new' ? null : editing} printers={printers.data ?? []} pending={save.isPending} error={save.error?.message ?? ''} onClose={() => setEditing(null)} onSave={(values) => save.mutate({ nozzle: editing === 'new' ? null : editing, values })} /> : null}
    {detailsNozzle ? <Modal title={`${detailsNozzle.nozzle_code} details`} description="Inspect this physical nozzle and use all available lifecycle actions." size="wide" onClose={() => setDetailsNozzle(null)} footer={<button className="button button--primary" onClick={() => setDetailsNozzle(null)}>Done</button>}>{renderDetailedNozzle(detailsNozzle)}</Modal> : null}
    {selected ? <Modal title={`${selected.nozzle_code} lifecycle`} description="Append-only installation, removal, retirement, and reactivation history." onClose={() => setSelected(null)} footer={<button className="button button--primary" onClick={() => setSelected(null)}>Done</button>}>{events.isLoading ? <LoadingState /> : events.data?.length ? <div className="mobile-card-list mobile-card-list--always">{events.data.map((event) => <article className="mobile-data-card" key={event.id}><strong>{titleCase(event.event_type)}</strong><span>{printers.data?.find((printer) => printer.id === event.printer_id)?.name ?? 'No printer'}</span><small>{dateTime(event.occurred_at)}{event.notes ? ` · ${event.notes}` : ''}</small></article>)}</div> : <p className="muted">No lifecycle events have been recorded yet.</p>}</Modal> : null}
  </div>
}
