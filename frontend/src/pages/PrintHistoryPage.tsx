import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock3, FileSearch, History, Star } from 'lucide-react'
import { type FormEvent, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import type { PrintJob, PrintQualityRating } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime, grams, titleCase } from '../lib/format'

const defectOptions = [
  'stringing', 'blobs_zits', 'underextrusion', 'overextrusion', 'poor_bridging',
  'poor_overhangs', 'warping', 'elephant_foot', 'weak_layer_adhesion',
  'poor_top_surface', 'dimensional_error', 'supports_difficult_to_remove',
  'supports_fused', 'seam_artifacts',
]

function snapshotLabel(snapshot: Record<string, unknown>, group: string, key: string) {
  const section = snapshot[group]
  return section && typeof section === 'object' && key in section
    ? String((section as Record<string, unknown>)[key] ?? '—')
    : '—'
}

function PrintAssessmentForm({ job, onSaved }: { job: PrintJob; onSaved: () => void }) {
  const latest = [...job.assessments].sort((left, right) => right.revision - left.revision)[0]
  const [rating, setRating] = useState<PrintQualityRating>(latest?.rating ?? 'successful')
  const [tags, setTags] = useState<string[]>(latest?.defect_tags ?? [])
  const [notes, setNotes] = useState(latest?.notes ?? '')
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: () => apiFetch(`/prints/${job.id}/assessments`, {
      method: 'POST',
      body: JSON.stringify({ rating, defect_tags: tags, notes: notes.trim() || null }),
    }),
    onSuccess: onSaved,
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Assessment could not be saved'),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    mutation.mutate()
  }

  return (
    <form className="assessment-form form-stack" onSubmit={submit}>
      <label>Outcome<select value={rating} onChange={(event) => setRating(event.target.value as PrintQualityRating)}><option value="excellent">Excellent</option><option value="successful">Successful</option><option value="acceptable">Acceptable</option><option value="failed">Failed</option></select></label>
      <fieldset className="defect-picker"><legend>Observed defects</legend>{defectOptions.map((tag) => <label key={tag} className="check-row"><input type="checkbox" checked={tags.includes(tag)} onChange={(event) => setTags((current) => event.target.checked ? [...current, tag] : current.filter((item) => item !== tag))} /><span>{titleCase(tag)}</span></label>)}</fieldset>
      <label>Notes <span className="label-optional">Optional</span><textarea rows={3} maxLength={4000} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
      {latest ? <small className="field-help">Saving creates revision {latest.revision + 1}; the earlier assessment remains immutable.</small> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <button className="button button--primary" disabled={mutation.isPending}><Star size={17} /> {mutation.isPending ? 'Saving…' : latest ? 'Revise assessment' : 'Save assessment'}</button>
    </form>
  )
}

function PrintDetail({ job, canAssess, onClose }: { job: PrintJob; canAssess: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const mismatches = job.inspection.mismatches ?? []
  const warnings = job.inspection.warnings ?? []
  return (
    <Modal title={job.filename} description="Immutable print context, inspection evidence, material changes, and outcome revisions." size="wide" onClose={onClose} footer={<button className="button" onClick={onClose}>Close</button>}>
      <div className="print-detail-grid">
        <section><p className="eyebrow">Exact material state</p><dl className="definition-list"><div><dt>Printer</dt><dd>{snapshotLabel(job.state_snapshot, 'printer', 'name')}</dd></div><div><dt>Spool</dt><dd>{snapshotLabel(job.state_snapshot, 'spool', 'code')}</dd></div><div><dt>Material</dt><dd>{job.material_name ?? snapshotLabel(job.state_snapshot, 'filament', 'product_name')}</dd></div><div><dt>Profile</dt><dd>{job.material_profile_id ? `Version ${job.material_profile_version}` : 'Legacy or unresolved'}</dd></div><div><dt>Build plate</dt><dd>{snapshotLabel(job.state_snapshot, 'build_plate_surface', 'code')}</dd></div><div><dt>G-code SHA-256</dt><dd className="hash-value">{job.gcode_sha256 ?? 'Unavailable'}</dd></div></dl></section>
        <section><p className="eyebrow">Sliced request</p><dl className="definition-list"><div><dt>Slicer</dt><dd>{[job.slicer, job.slicer_version].filter(Boolean).join(' ') || 'Unknown'}</dd></div><div><dt>Quality</dt><dd>{job.cura_quality_profile ?? 'Unknown'}</dd></div><div><dt>Nozzle / bed</dt><dd>{job.extruder_temp_c ?? '—'} / {job.bed_temp_c ?? '—'} °C</dd></div><div><dt>Layer / line</dt><dd>{job.layer_height_mm ?? '—'} / {job.line_width_mm ?? '—'} mm</dd></div><div><dt>Flow</dt><dd>{job.flow_percent ? `${job.flow_percent}%` : '—'}</dd></div><div><dt>Actual filament</dt><dd>{job.actual_filament_weight_g ? grams(job.actual_filament_weight_g) : 'Unavailable'}</dd></div></dl></section>
      </div>
      <section className="inspection-panel"><div className="section-heading"><div><p className="eyebrow">G-code inspection</p><h3>{titleCase(job.inspection_status)}</h3></div><StatusPill status={job.inspection_status} /></div>{mismatches.map((mismatch) => <p key={mismatch.field} className="form-error"><AlertTriangle size={16} /> {mismatch.label}: G-code {mismatch.gcode_value}; profile {mismatch.profile_value}</p>)}{warnings.map((message) => <p key={message} className="warning-note"><AlertTriangle size={16} /> {message}</p>)}{!mismatches.length && !warnings.length ? <p className="success-note"><CheckCircle2 size={17} /> The inspected settings match the exact managed profile.</p> : null}</section>
      <section><p className="eyebrow">Material segments</p><div className="mobile-card-list mobile-card-list--always">{job.segments.length ? job.segments.map((segment) => <article className="mobile-data-card" key={segment.id}><strong>Segment {segment.segment_number} · {titleCase(segment.source)}</strong><span>Spool {snapshotLabel(segment.state_snapshot, 'spool', 'code')}</span><small>{dateTime(segment.started_at)} – {dateTime(segment.ended_at)}</small></article>) : <p className="muted">No exact segments were recoverable for this print.</p>}</div></section>
      {canAssess && job.status !== 'in_progress' ? <section><p className="eyebrow">Print outcome</p><PrintAssessmentForm job={job} onSaved={async () => { await queryClient.invalidateQueries({ queryKey: ['prints'] }); onClose() }} /></section> : null}
      {job.assessments.length ? <section><p className="eyebrow">Assessment history</p>{[...job.assessments].sort((left, right) => right.revision - left.revision).map((assessment) => <p key={assessment.id}><strong>Revision {assessment.revision}: {titleCase(assessment.rating)}</strong> · {assessment.defect_tags.map(titleCase).join(', ') || 'No defects'}<br /><small>{dateTime(assessment.created_at)}{assessment.notes ? ` · ${assessment.notes}` : ''}</small></p>)}</section> : null}
    </Modal>
  )
}

export default function PrintHistoryPage() {
  const { user } = useAuth()
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<PrintJob | null>(null)
  const query = useQuery({
    queryKey: ['prints', status],
    queryFn: () => apiFetch<PrintJob[]>(`/prints?limit=250${status ? `&print_status=${status}` : ''}`),
    refetchInterval: 15_000,
  })
  const jobs = useMemo(() => query.data ?? [], [query.data])
  return <div>
    <PageHeader eyebrow="Canonical production record" title="Print history" description="Inspect each job against its exact profile, spool, plate, G-code, material segments, and recorded outcome." />
    <section className="toolbar"><label className="select-field"><History size={17} /><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All outcomes</option><option value="in_progress">In progress</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="cancelled">Cancelled</option><option value="legacy_unknown">Unknown print status</option></select></label><span className="toolbar__summary">{jobs.length} print records</span></section>
    {query.isLoading ? <LoadingState label="Loading print history" /> : !jobs.length ? <EmptyState icon={FileSearch} title="No print history yet" description="Moonraker history and new exact-state prints will appear here automatically." /> : <>
      <div className="table-card desktop-data-table"><table><thead><tr><th>Print</th><th>Material state</th><th>Inspection</th><th>Outcome</th><th>Started</th><th>Duration</th></tr></thead><tbody>{jobs.map((job) => { const latest = [...job.assessments].sort((left, right) => right.revision - left.revision)[0]; return <tr key={job.id} onClick={() => setSelected(job)} tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && setSelected(job)}><td><strong>{job.filename}</strong><small className="table-subtext">{job.slicer ?? titleCase(job.source)}</small></td><td>{job.material_name ?? job.material_type ?? 'Unresolved'}<small className="table-subtext">{job.material_profile_version ? `Profile v${job.material_profile_version}` : 'No exact profile'}</small></td><td><StatusPill status={job.inspection_status} /></td><td><StatusPill status={latest?.rating ?? job.status} /></td><td>{dateTime(job.started_at)}</td><td>{job.print_duration_seconds ? `${Math.round(Number(job.print_duration_seconds) / 60)} min` : '—'}</td></tr>})}</tbody></table></div>
      <div className="mobile-card-list">{jobs.map((job) => <button className="mobile-data-card mobile-data-card--button" key={job.id} onClick={() => setSelected(job)}><span className="mobile-data-card__heading"><strong>{job.filename}</strong><StatusPill status={job.inspection_status} /></span><span>{job.state_snapshot.legacy_unresolved === true ? 'Legacy record · exact material state unavailable' : `${job.material_name ?? job.material_type ?? 'Unresolved material'} · ${job.material_profile_version ? `profile v${job.material_profile_version}` : 'no exact profile'}`}</span><small><Clock3 size={14} /> {dateTime(job.started_at)}</small></button>)}</div>
    </>}
    {selected ? <PrintDetail job={selected} canAssess={user?.role !== 'viewer'} onClose={() => setSelected(null)} /> : null}
  </div>
}
