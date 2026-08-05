import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Boxes, CheckCircle2, Filter, QrCode, Scale, Search, Star } from 'lucide-react'
import { type CSSProperties, type FormEvent, useMemo, useState } from 'react'
import { ApiClientError, apiFetch, idempotencyKey } from '../api/client'
import type { Page, Spool } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime, grams, percent } from '../lib/format'

function WeighModal({ spool, onClose }: { spool: Spool; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [grossMass, setGrossMass] = useState('')
  const [tareMass, setTareMass] = useState(Number(spool.tare_mass_g) > 0 ? spool.tare_mass_g : '')
  const [notes, setNotes] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [override, setOverride] = useState(false)
  const [error, setError] = useState('')
  const net = grossMass && tareMass ? Math.max(0, Number(grossMass) - Number(tareMass)) : null

  const mutation = useMutation({
    mutationFn: () => apiFetch(`/spools/${spool.id}/measurements`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey(`weigh-${spool.id}`) },
      body: JSON.stringify({
        gross_mass_g: grossMass,
        tare_mass_g: Number(spool.tare_mass_g) > 0 ? null : tareMass,
        source: 'manual',
        confirmed,
        allow_above_nominal: override,
        notes: notes || null,
      }),
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['spools'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
      onClose()
    },
    onError: (caught) => {
      if (caught instanceof ApiClientError && caught.code === 'measurement_confirmation_required') {
        setConfirmed(true)
        setError('This is an increase from the expected amount. Review the values, then submit again to confirm the correction.')
      } else setError(caught instanceof Error ? caught.message : 'The measurement could not be saved')
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    mutation.mutate()
  }

  return (
    <Modal title={`Weigh ${spool.spool_code}`} description="Enter the complete spool weight. Tare is deducted automatically." onClose={onClose} footer={<><button className="button" onClick={onClose}>Cancel</button><button className="button button--primary" form="weigh-form" disabled={mutation.isPending || !grossMass}><Scale size={17} />{confirmed ? 'Confirm measurement' : 'Record measurement'}</button></>}>
      <form id="weigh-form" className="form-stack" onSubmit={(event) => void submit(event)}>
        <div className="spool-identity-callout"><span className="filament-swatch" style={{ '--swatch': `#${spool.color_hex ?? '2F80A5'}` } as CSSProperties} /><div><strong>{spool.vendor_name ?? 'Unspecified'} {spool.material_type}</strong><span>{spool.color_name} · expected {grams(spool.remaining_mass_expected_g)}</span></div></div>
        <label>Gross weight (grams)<div className="input-suffix"><input type="number" min="0" step="0.1" inputMode="decimal" value={grossMass} onChange={(event) => setGrossMass(event.target.value)} autoFocus required /><span>g</span></div></label>
        {Number(spool.tare_mass_g) <= 0 && <label>Verified empty-spool tare<div className="input-suffix"><input type="number" min="0.1" step="0.1" inputMode="decimal" value={tareMass} onChange={(event) => setTareMass(event.target.value)} required /><span>g</span></div><small className="field-help">This establishes the previously unknown tare and is preserved with the measurement.</small></label>}
        <div className="measurement-math"><span><small>{Number(spool.tare_mass_g) > 0 ? 'Stored tare' : 'New tare'}</small><strong>{tareMass ? grams(tareMass, 1) : '—'}</strong></span><span className="math-symbol">−</span><span><small>Calculated filament</small><strong>{net == null ? '—' : grams(net, 1)}</strong></span></div>
        <label>Notes <span className="label-optional">Optional</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} maxLength={4000} placeholder="Scale, reason for correction, or other context" /></label>
        {confirmed && <label className="check-row"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span><strong>Confirm unexpected increase</strong><small>This preserves the correction in the audit trail.</small></span></label>}
        {user?.role === 'administrator' && net != null && net > Number(spool.nominal_net_mass_g) && <label className="check-row"><input type="checkbox" checked={override} onChange={(event) => setOverride(event.target.checked)} /><span><strong>Allow value above nominal capacity</strong><small>Administrator override; use only after verifying the tare and scale.</small></span></label>}
        {error && <p className="form-error" role="alert">{error}</p>}
      </form>
    </Modal>
  )
}

export default function SpoolsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const canEdit = user?.role !== 'viewer'
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<Spool | null>(null)
  const [weighing, setWeighing] = useState<Spool | null>(null)
  const [actionError, setActionError] = useState('')
  const query = useQuery({
    queryKey: ['spools', search, status],
    queryFn: () => apiFetch<Page<Spool>>(`/spools?limit=200${search ? `&search=${encodeURIComponent(search)}` : ''}${status ? `&status=${encodeURIComponent(status)}` : ''}`),
  })
  const items = useMemo(() => query.data?.items ?? [], [query.data?.items])
  const setActive = useMutation({
    mutationFn: (spool: Spool) => apiFetch(`/spools/${spool.id}/set-active`, { method: 'POST' }),
    onSuccess: async () => {
      setActionError('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['spools'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
    },
    onError: (caught) => setActionError(caught instanceof Error ? caught.message : 'Could not queue active spool'),
  })
  const needsAttention = useMemo(() => items.filter((spool) => spool.status === 'needs_weighing' || spool.status === 'low').length, [items])

  return (
    <div>
      <PageHeader eyebrow="Physical inventory" title="Spools" description="Track each labeled spool, its trustworthy remaining mass, and its projection state." actions={canEdit && selected ? <button className="button button--primary" onClick={() => setWeighing(selected)}><Scale size={17} /> Weigh selected</button> : undefined} />
      <section className="toolbar">
        <label className="search-field"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search code, material, color, or location" aria-label="Search spools" /></label>
        <label className="select-field"><Filter size={17} /><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by status"><option value="">All statuses</option><option value="needs_weighing">Needs weighing</option><option value="in_stock">In stock</option><option value="low">Low</option><option value="empty">Empty</option></select></label>
        <span className="toolbar__summary">{query.data?.total ?? 0} spools · {needsAttention} need attention</span>
      </section>

      {query.isLoading ? <LoadingState label="Loading spools" /> : items.length === 0 ? <EmptyState icon={Boxes} title="No spools found" description="Adjust the filters or import the master workbook to establish inventory." /> : (
        <div className="inventory-layout">
          <div className="table-card">
            <table>
              <thead><tr><th>Spool</th><th>Material</th><th>Remaining</th><th>Status</th><th>Location</th><th>Last weighed</th></tr></thead>
              <tbody>{items.map((spool) => <tr key={spool.id} className={selected?.id === spool.id ? 'table-row--selected' : ''} onClick={() => setSelected(spool)} tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && setSelected(spool)}><td><div className="table-identity"><span className="filament-swatch" style={{ '--swatch': `#${spool.color_hex ?? '2F80A5'}` } as CSSProperties} /><span><strong>{spool.spool_code}</strong><small>{spool.vendor_name ?? 'No vendor'}</small></span></div></td><td><strong>{spool.material_type}{spool.filler ? ` ${spool.filler}` : ''}</strong><small className="table-subtext">{spool.color_name}</small></td><td><div className="table-progress"><span><strong>{grams(spool.remaining_mass_effective_g)}</strong><small>{percent(spool.remaining_percent)}</small></span><div className="progress progress--small"><span style={{ width: `${Math.min(100, Number(spool.remaining_percent))}%` }} /></div></div></td><td><StatusPill status={spool.status} /></td><td>{spool.location ?? '—'}</td><td>{dateTime(spool.last_measurement_at)}</td></tr>)}</tbody>
            </table>
          </div>

          <aside className={`detail-panel${selected ? ' detail-panel--open' : ''}`}>
            {selected ? <><header className="detail-panel__header"><div className="table-identity"><span className="filament-swatch filament-swatch--large" style={{ '--swatch': `#${selected.color_hex ?? '2F80A5'}` } as CSSProperties} /><span><p className="eyebrow">Selected spool</p><h2>{selected.spool_code}</h2></span></div><StatusPill status={selected.status} /></header><div className="detail-panel__body"><dl className="definition-list"><div><dt>Filament</dt><dd>{selected.vendor_name} {selected.material_type} · {selected.color_name}</dd></div><div><dt>Remaining</dt><dd>{grams(selected.remaining_mass_effective_g)} / {grams(selected.nominal_net_mass_g)}</dd></div><div><dt>Confidence</dt><dd>{selected.weight_confidence}</dd></div><div><dt>Tare mass</dt><dd>{Number(selected.tare_mass_g) > 0 ? grams(selected.tare_mass_g, 1) : 'Unknown'}</dd></div><div><dt>Spoolman</dt><dd>{selected.spoolman_id ? `ID ${selected.spoolman_id}` : 'Projection pending'}</dd></div><div><dt>Location</dt><dd>{selected.location ?? 'Not set'}</dd></div></dl><div className="detail-actions">{canEdit && <button className="button button--primary" onClick={() => setWeighing(selected)}><Scale size={17} /> Weigh spool</button>}{canEdit && <button className="button" disabled={!selected.spoolman_id || setActive.isPending} title={!selected.spoolman_id ? 'Project this spool to Spoolman first' : undefined} onClick={() => setActive.mutate(selected)}><Star size={17} /> Set active</button>}<a className="button" href={`/api/v1/spools/${selected.id}/label`} target="_blank" rel="noreferrer"><QrCode size={17} /> View label</a></div>{actionError && <p className="form-error">{actionError}</p>}{selected.weight_confidence === 'measured' && <p className="success-note"><CheckCircle2 size={17} /> Physical measurement is the trusted remaining value.</p>}</div></> : <EmptyState icon={Boxes} title="Select a spool" description="Choose a row to inspect its trusted mass and available actions." />}
          </aside>
        </div>
      )}
      {weighing && <WeighModal spool={weighing} onClose={() => { setWeighing(null); setSelected(null) }} />}
    </div>
  )
}
