import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, MaterialTemplate, Printer } from '../api/types'
import { compactNumber } from '../lib/format'
import { EditorSection } from './EditorSection'
import { Modal } from './Modal'

type Ratings = { record_version: number; ratings: Record<string, number> }
type Compatibility = Ratings & {
  template_id: string | null
  template_name: string | null
  printer_id: string
  printer_name: string
  active_plate_id: string | null
  inherited_ratings: Record<string, number>
  overrides: Record<string, number>
}

export function ratingLabel(rating: number | undefined) {
  return rating == null ? 'Unrated' : rating === 0 ? '0 stars · Do not use — printing blocked' : `${'★'.repeat(rating)}${'☆'.repeat(5 - rating)} · ${rating} / 5`
}

/** Keyboard-accessible stars announce numeric values instead of glyphs. */
function StarControl({ plate, value, disabled, onChange }: { plate: BuildPlate; value?: number; disabled: boolean; onChange: (value: number) => void }) {
  return <div className="plate-star-control" role="group" aria-label={`Rating for ${plate.plate_code}`}>
    <button type="button" className="button" aria-label={`Rate ${plate.plate_code} 0 stars — do not use`} aria-pressed={value === 0} disabled={disabled} onClick={() => onChange(0)}>0 · Avoid</button>
    <div className="plate-stars">{[1, 2, 3, 4, 5].map((stars) => <button key={stars} type="button" className={`plate-star${value != null && stars <= value ? ' plate-star--filled' : ''}`} aria-label={`Rate ${plate.plate_code} ${stars} ${stars === 1 ? 'star' : 'stars'}`} aria-pressed={value === stars} disabled={disabled} onClick={() => onChange(stars)}>{value != null && stars <= value ? '★' : '☆'}</button>)}</div>
  </div>
}

/** Save sparse ownership only; inherited ratings never become overrides on refresh. */
export function PlateRatingEditor({ templateId, filamentId, plates, inherited = {}, readOnly = false }: { templateId?: string; filamentId?: string; plates: BuildPlate[]; inherited?: Record<string, number>; readOnly?: boolean }) {
  const client = useQueryClient()
  const path = filamentId ? `/build-plate-ratings/filament/${filamentId}/overrides` : `/build-plate-ratings/${templateId}`
  const key = ['plate-ratings', filamentId ? 'filament' : 'template', filamentId ?? templateId]
  const query = useQuery({ queryKey: key, queryFn: () => apiFetch<Ratings>(path) })
  const save = useMutation({
    mutationFn: ({ plateId, value }: { plateId: string; value: number | undefined }) => {
      if (!query.data) throw new Error('Load ratings before saving')
      const ratings = { ...query.data.ratings }
      if (value === undefined || (filamentId && value === inherited[plateId])) delete ratings[plateId]
      else ratings[plateId] = value
      return apiFetch<Ratings>(path, { method: 'PUT', body: JSON.stringify({ expected_version: query.data.record_version, ratings }) })
    },
    onSuccess: (data) => {
      client.setQueryData(key, data)
      void client.invalidateQueries({ queryKey: ['plate-compatibility'] })
    },
  })
  const effective = { ...inherited, ...query.data?.ratings }
  const best = Math.max(0, ...plates.filter((plate) => plate.status === 'active').map((plate) => effective[plate.id] ?? 0))
  return <div className="template-rating-section"><EditorSection title="Build plate ratings" description={filamentId ? 'Inherits the linked template. Select stars to customize this filament; Revert to Template restores live inheritance. Changes save immediately.' : 'One rating per whole plate, shared by both sides. Changes save immediately and update inheriting filaments. Zero stars blocks managed print starts; Unrated remains allowed.'}>
    {query.isPending && <p role="status">Loading ratings…</p>}
    {!plates.length && <p className="muted">Add a build plate to begin ranking.</p>}
    <div className="plate-rating-list">{plates.map((plate) => {
      const custom = filamentId != null && Object.hasOwn(query.data?.ratings ?? {}, plate.id)
      const value = effective[plate.id]
      return <div key={plate.id} className={`plate-rating-row${value === 0 ? ' plate-rating-row--blocked' : ''}`}>
        <div><strong>{plate.plate_code} · {plate.display_name}</strong><small className="table-subtext">{ratingLabel(value)}{value != null && value > 0 && value === best && plate.status === 'active' ? ' · Recommended' : ''}{plate.status !== 'active' ? ' · Unavailable' : ''}</small>{filamentId && <small className={custom ? 'profile-ownership profile-ownership--customized' : 'profile-ownership'}>{custom ? 'Customized' : 'Inherited'}</small>}</div>
        {!readOnly && <div><StarControl plate={plate} value={value} disabled={!query.data || save.isPending} onChange={(next) => save.mutate({ plateId: plate.id, value: next })} /><button type="button" className="text-link" disabled={!query.data || save.isPending || (filamentId ? !custom : value == null)} onClick={() => save.mutate({ plateId: plate.id, value: undefined })}>{filamentId ? `Revert to Template for ${plate.plate_code}` : `Clear ${plate.plate_code} to Unrated`}</button></div>}
      </div>
    })}</div>
    {(query.error || save.error) && <p className="form-error" role="alert">{(query.error || save.error)?.message}</p>}
    {save.isSuccess && <small role="status">Ratings saved.</small>}
  </EditorSection></div>
}

/** Catalog entry point separate from unrelated print-setting controls. */
export function TemplatePlateRatingsButton({ templates, plates, printers = [], readOnly = false }: { templates: MaterialTemplate[]; plates: BuildPlate[]; printers?: Printer[]; readOnly?: boolean }) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState('')
  const current = templates.find((template) => template.id === selected) ?? templates.find((template) => template.active)
  return <><button type="button" className="button" onClick={() => setOpen(true)}>★ Build plate ratings</button>{open && <Modal title="Build plate ratings by material template" size="wide" onClose={() => setOpen(false)} footer={<button className="button" onClick={() => setOpen(false)}>Done</button>}><label>Material template<select value={current?.id ?? ''} onChange={(event) => setSelected(event.target.value)}>{templates.filter((template) => template.active).map((template) => <option key={template.id} value={template.id}>{template.name} · {printers.find((printer) => printer.id === template.printer_id)?.name ?? 'Printer unavailable'} · {compactNumber(template.nozzle_diameter_mm, 1)} mm</option>)}</select></label>{current ? <PlateRatingEditor key={current.id} templateId={current.id} plates={plates} readOnly={readOnly} /> : <p>No active templates available.</p>}</Modal>}</>
}

/** Advice uses the same effective map as preflight, with no external printer reads. */
export function PlateCompatibility({ filamentId, printerId, activeSideId, editable = false }: { filamentId: string; printerId?: string; activeSideId?: string; editable?: boolean }) {
  const [open, setOpen] = useState(false)
  const [selectedPrinter, setSelectedPrinter] = useState('')
  const query = useQuery({ queryKey: ['plate-compatibility', filamentId, printerId, activeSideId], queryFn: () => apiFetch<Compatibility[]>(`/build-plate-ratings/filament/${filamentId}${printerId ? `?printer_id=${printerId}` : ''}`), staleTime: 10000, refetchInterval: 10000 })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  if (query.isPending) return <small className="muted">Loading build plate ratings…</small>
  if (query.error || plates.error) return <small className="form-error">Build plate compatibility unavailable</small>
  const scopes = query.data ?? []
  const scope = scopes.find((item) => item.printer_id === selectedPrinter) ?? scopes[0]
  return <div className="plate-compatibility">{scopes.map((item) => {
    const active = item.active_plate_id ? item.ratings[item.active_plate_id] : undefined
    const ranked = (plates.data ?? []).filter((plate) => plate.status === 'active' && (item.ratings[plate.id] ?? 0) > 0).sort((a, b) => item.ratings[b.id] - item.ratings[a.id] || a.plate_code.localeCompare(b.plate_code, undefined, { numeric: true }))
    const best = ranked[0] ? item.ratings[ranked[0].id] : undefined
    const recommended = ranked.filter((plate) => item.ratings[plate.id] === best)
    const better = active != null && best != null && best > active
    return <div key={item.printer_id} className={active === 0 ? 'form-error' : better ? 'warning-note' : 'muted'} role={active === 0 || better ? 'alert' : undefined}>
      <small>{item.printer_name} · Active plate: {ratingLabel(active)}</small>
      {active === 0 && <strong className="table-subtext">Do NOT use this build plate with this filament. Printing is blocked.</strong>}
      {better && active !== 0 && <strong className="table-subtext">A better-rated build plate is available.</strong>}
      {recommended.length > 0 && <small className="table-subtext">Recommended: {recommended.map((plate) => `${plate.plate_code} · ${plate.display_name}`).join(', ')} — {ratingLabel(best)}</small>}
      {active == null && recommended.length > 0 && <small className="table-subtext">The active plate is unrated; use a rated recommendation when possible.</small>}
    </div>
  })}<button type="button" className="text-link" onClick={() => setOpen(true)}>{editable ? '★ View / edit build plate ratings' : '★ View all build plate ratings'}</button>
    {open && <Modal title="Filament build plate ratings" size="wide" onClose={() => setOpen(false)} footer={<button className="button" onClick={() => setOpen(false)}>Done</button>}>
      {scopes.length > 1 && <label>Printer template scope<select value={scope?.printer_id ?? ''} onChange={(event) => setSelectedPrinter(event.target.value)}>{scopes.map((item) => <option key={item.printer_id} value={item.printer_id}>{item.printer_name} · {item.template_name ?? 'No linked template'}</option>)}</select></label>}
      <p className="muted">{scope?.template_name ? `Inherited from ${scope.template_name}.` : 'No template is linked for the current printer/nozzle.'} Filament overrides apply on every printer and remain when its template changes.</p>
      <PlateRatingEditor filamentId={filamentId} plates={plates.data ?? []} inherited={scope?.inherited_ratings} readOnly={!editable} />
    </Modal>}
  </div>
}
