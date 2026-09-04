import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ChevronFirst, ChevronLast, ChevronLeft, ChevronRight, Clock3, ExternalLink, FileSearch, History, Printer as PrinterIcon, Rows3, SlidersHorizontal, Star } from 'lucide-react'
import { type FormEvent, useMemo, useState } from 'react'
import { actionableApiError, apiFetch } from '../api/client'
import type { Printer, PrintJob, PrintJobPage, PrintJobSummary, PrintQualityRating } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { compactNumber, costPerGram, currencyAmount, dateTime, grams, titleCase } from '../lib/format'

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

function historicalMaterialLabel(job: PrintJobSummary) {
  const filament = recordValue(job.state_snapshot.filament)
  const parts = [
    filament?.material_type ?? job.material_type,
    filament?.color_name,
    filament?.filler,
    filament?.finish,
  ]
  return parts
    .filter((value) => value != null && String(value).trim() && !['none', 'standard', 'no filler', 'no finish', 'not specified'].includes(String(value).trim().toLowerCase()))
    .map(String)
    .join(' · ') || job.material_name || 'Unresolved material'
}

function duration(value: string | null) {
  if (!value) return '—'
  const seconds = Number(value)
  if (!Number.isFinite(seconds)) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  return hours ? `${hours} hr ${minutes} min` : `${minutes} min`
}

function variance(actual: string | null, expected: string | null) {
  if (actual == null || expected == null || Number(expected) === 0) return null
  const difference = ((Number(actual) - Number(expected)) / Number(expected)) * 100
  if (!Number.isFinite(difference)) return null
  return `${difference >= 0 ? '+' : ''}${difference.toFixed(0)}% vs estimate`
}

function printOutcome(job: PrintJobSummary) {
  const latest = [...job.assessments].sort((left, right) => right.revision - left.revision)[0]
  return latest?.rating ?? job.moonraker_status ?? job.status
}

function pageSummary(page: PrintJobPage) {
  if (page.total_items === 0) return '0 print records'
  const first = (page.page - 1) * page.per_page + 1
  const last = Math.min(page.page * page.per_page, page.total_items)
  return `${first}–${last} of ${page.total_items} print records`
}

function printOutcomeClass(job: PrintJobSummary) {
  if (job.status === 'completed') return 'print-history-entry--successful'
  if (job.status === 'cancelled') return 'print-history-entry--cancelled'
  if (job.status === 'failed') return 'print-history-entry--failed'
  return ''
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function printSettingRows(settings: Record<string, unknown>) {
  const rows: Array<[string, unknown]> = []
  for (const [key, value] of Object.entries(settings)) {
    if (key === 'cura_extensions' && recordValue(value)) {
      for (const [extensionKey, extensionValue] of Object.entries(recordValue(value) ?? {})) {
        rows.push([extensionKey, extensionValue])
      }
    } else rows.push([key, value])
  }
  return rows.sort(([left], [right]) => left.localeCompare(right))
}

function printSettingValue(value: unknown) {
  if (value == null || value === '') return 'Not set'
  if (typeof value === 'boolean') return value ? 'Enabled' : 'Disabled'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function PrintSettingsTable({ settings, empty }: { settings: Record<string, unknown>; empty: string }) {
  const rows = printSettingRows(settings)
  if (!rows.length) return <p className="muted">{empty}</p>
  return <div className="print-settings-table"><table><thead><tr><th>Setting</th><th>Saved value</th></tr></thead><tbody>{rows.map(([key, value]) => <tr key={key}><td>{titleCase(key)}</td><td><code>{printSettingValue(value)}</code></td></tr>)}</tbody></table></div>
}

function AdvancedPrintSettings({ job, onBack, onClose }: { job: PrintJob; onBack: () => void; onClose: () => void }) {
  const snapshot = recordValue(job.print_settings_snapshot)
  const managed = recordValue(snapshot?.managed)
  const template = recordValue(managed?.template)
  const resolved = recordValue(managed?.resolved) ?? {}
  const differences = recordValue(managed?.differences) ?? {}
  const differenceKeys = Array.isArray(managed?.difference_keys) ? managed.difference_keys.map(String) : []
  const cura = recordValue(snapshot?.cura)
  const globalScope = recordValue(cura?.global)
  const extruders = Array.isArray(cura?.extruders)
    ? cura.extruders.map(recordValue).filter((scope): scope is Record<string, unknown> => scope !== null)
    : []
  const curaAvailable = cura?.available === true
  const reason = cura?.reason === 'not_embedded'
    ? 'This G-code did not contain a Cura SETTING_3 document.'
    : cura?.reason === 'payload_too_large'
      ? 'The embedded Cura settings exceeded the safe capture limit.'
      : cura?.reason === 'invalid_payload'
        ? 'The embedded Cura settings could not be safely decoded.'
        : 'A safely bounded G-code inspection was unavailable for this print.'
  return <Modal title="Advanced print settings" description={`Immutable settings captured for ${job.filename}. Cura formulas are preserved as text and are never evaluated.`} size="wide" onClose={onBack} footer={<><button className="button" type="button" onClick={onBack}>Back to print</button><button className="button button--primary" type="button" onClick={onClose}>Close</button></>}>
    <section className="print-settings-summary"><div><span>Material differences</span><strong>{differenceKeys.length}</strong></div><div><span>Resolved material settings</span><strong>{printSettingRows(resolved).length}</strong></div><div><span>Cura settings</span><strong>{Number(cura?.setting_count ?? 0).toLocaleString()}</strong></div></section>
    <details className="print-settings-group" open><summary><span>Different from template</span><small>{differenceKeys.length ? `${differenceKeys.length} saved difference${differenceKeys.length === 1 ? '' : 's'}` : 'Fully inherited'}</small></summary><PrintSettingsTable settings={differences} empty="Every saved material value matched the linked template at print time." /></details>
    <details className="print-settings-group"><summary><span>Resolved Filament Manager settings</span><small>Exact values used for comparison</small></summary>{managed ? <PrintSettingsTable settings={resolved} empty="No resolved material settings were captured." /> : <p className="muted">This legacy or unresolved print has no exact managed profile snapshot.</p>}</details>
    <details className="print-settings-group"><summary><span>Template at print time</span><small>{template ? `${String(template.name ?? 'Template')} · version ${String(template.version ?? 'unknown')}` : 'Unavailable'}</small></summary><PrintSettingsTable settings={recordValue(template?.settings) ?? {}} empty="No linked template snapshot was available." /></details>
    <section className="print-settings-source"><div className="section-heading"><div><p className="eyebrow">Cura G-code settings</p><h3>{curaAvailable ? 'Embedded SETTING_3 values' : 'Not available'}</h3></div>{curaAvailable ? <StatusPill status="captured" /> : <StatusPill status="unavailable" />}</div>
      {!curaAvailable ? <p className="warning-note"><AlertTriangle size={16} /> {reason}</p> : <>
        {cura?.truncated === true ? <p className="warning-note"><AlertTriangle size={16} /> The capture reached a safety limit. Stored values remain usable, but the embedded set was not complete.</p> : null}
        {Number(cura?.filtered_count ?? 0) > 0 ? <p className="warning-note"><AlertTriangle size={16} /> {Number(cura?.filtered_count).toLocaleString()} unsafe or unsupported value(s) were omitted.</p> : null}
        {globalScope ? <details className="print-settings-group"><summary><span>Global quality</span><small>{String(globalScope.name ?? globalScope.definition ?? 'Cura global scope')}</small></summary><PrintSettingsTable settings={recordValue(globalScope.settings) ?? {}} empty="No global values were embedded." /></details> : null}
        {extruders.map((scope, index) => <details className="print-settings-group" key={`${String(scope.position ?? index)}-${index}`}><summary><span>Extruder {String(scope.position ?? index)}</span><small>{String(scope.name ?? scope.definition ?? 'Cura extruder scope')}</small></summary><PrintSettingsTable settings={recordValue(scope.settings) ?? {}} empty="No extruder values were embedded." /></details>)}
      </>}
    </section>
  </Modal>
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
      {latest ? <small className="field-help">Saving updates the current outcome while retaining the earlier assessment in history.</small> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <button className="button button--primary" disabled={mutation.isPending}><Star size={17} /> {mutation.isPending ? 'Saving…' : latest ? 'Update assessment' : 'Save assessment'}</button>
    </form>
  )
}

function PrintDetail({ job, canAssess, onClose }: { job: PrintJob; canAssess: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [showSettings, setShowSettings] = useState(false)
  const mismatches = job.inspection.mismatches ?? []
  const warnings = job.inspection.warnings ?? []
  const metadata = job.inspection.file_metadata ?? {}
  const nozzleDetails = [
    snapshotLabel(job.state_snapshot, 'nozzle', 'code'),
    job.nozzle_diameter_mm ? `${compactNumber(job.nozzle_diameter_mm, 2)} mm` : null,
    snapshotLabel(job.state_snapshot, 'nozzle', 'material'),
  ].filter((value) => value && value !== '—').join(' · ') || 'Legacy or unresolved'
  if (showSettings) return <AdvancedPrintSettings job={job} onBack={() => setShowSettings(false)} onClose={onClose} />
  return (
    <Modal title={job.filename} description="Immutable print context, inspection evidence, material changes, and outcome history." size="wide" onClose={onClose} footer={<><button className="button" type="button" onClick={() => setShowSettings(true)}><SlidersHorizontal size={16} /> Advanced print settings</button><button className="button button--primary" onClick={onClose}>Close</button></>}>
      {job.thumbnail_url ? <img className="print-thumbnail" src={job.thumbnail_url} alt={`Preview of ${job.filename}`} /> : null}
      <div className="print-detail-grid">
        <section><p className="eyebrow">Exact physical state</p><dl className="definition-list"><div><dt>Printer</dt><dd>{snapshotLabel(job.state_snapshot, 'printer', 'name')}</dd></div><div><dt>Nozzle</dt><dd>{nozzleDetails}</dd></div><div><dt>Spool</dt><dd>{snapshotLabel(job.state_snapshot, 'spool', 'code')}</dd></div><div><dt>Material</dt><dd>{historicalMaterialLabel(job)}</dd></div><div><dt>Profile</dt><dd>{job.material_profile_id ? `Exact saved settings · version ${job.material_profile_version ?? 'unknown'}` : 'Legacy or unresolved'}</dd></div><div><dt>Build plate</dt><dd>{snapshotLabel(job.state_snapshot, 'build_plate_surface', 'code')}</dd></div></dl></section>
        <section><p className="eyebrow">Sliced request</p><dl className="definition-list"><div><dt>Slicer</dt><dd>{[job.slicer, job.slicer_version].filter(Boolean).join(' ') || 'Unknown'}</dd></div><div><dt>Quality / machine</dt><dd>{[job.cura_quality_profile, job.machine_name].filter(Boolean).join(' · ') || 'Unknown'}</dd></div><div><dt>Nozzle / initial bed / bed / chamber</dt><dd>{compactNumber(job.extruder_temp_c, 0)} / {compactNumber(job.initial_bed_temp_c, 0)} / {compactNumber(job.bed_temp_c, 0)} / {compactNumber(job.chamber_temp_c, 0)} °C</dd></div><div><dt>Layer / line</dt><dd>{compactNumber(job.layer_height_mm, 2)} / {compactNumber(job.line_width_mm, 2)} mm</dd></div><div><dt>Speed / flow</dt><dd>{job.print_speed_mm_s ? `${compactNumber(job.print_speed_mm_s, 0)} mm/s` : '—'} / {job.flow_percent ? `${compactNumber(job.flow_percent, 0)}%` : '—'}</dd></div><div><dt>Retraction</dt><dd>{job.retraction_distance_mm ? `${compactNumber(job.retraction_distance_mm, 2)} mm` : '—'} / {job.retraction_speed_mm_s ? `${compactNumber(job.retraction_speed_mm_s, 0)} mm/s` : '—'}</dd></div><div><dt>Pressure advance</dt><dd>{compactNumber(job.pressure_advance, 2)}</dd></div></dl></section>
        <section><p className="eyebrow">Job results</p><dl className="definition-list"><div><dt>Outcome</dt><dd><StatusPill status={printOutcome(job)} /></dd></div><div><dt>Started / finished</dt><dd>{dateTime(job.started_at)} / {dateTime(job.ended_at)}</dd></div><div><dt>Estimated / print / total</dt><dd>{duration(job.estimated_duration_seconds)} / {duration(job.print_duration_seconds)} / {duration(job.total_duration_seconds)}{variance(job.print_duration_seconds, job.estimated_duration_seconds) ? <small className="table-subtext">{variance(job.print_duration_seconds, job.estimated_duration_seconds)}</small> : null}</dd></div><div><dt>Predicted filament</dt><dd>{job.predicted_filament_weight_g ? grams(job.predicted_filament_weight_g, 1) : job.predicted_filament_length_mm ? `${compactNumber(job.predicted_filament_length_mm, 0)} mm` : 'Unavailable'}{job.predicted_filament_cost ? <small className="table-subtext">{currencyAmount(job.predicted_filament_cost, job.cost_currency ?? 'USD')} estimated</small> : null}</dd></div><div><dt>Actual filament</dt><dd>{job.actual_filament_weight_g ? grams(job.actual_filament_weight_g, 1) : job.actual_filament_length_mm ? `${compactNumber(job.actual_filament_length_mm, 0)} mm` : 'Unavailable'}{variance(job.actual_filament_weight_g, job.predicted_filament_weight_g) ? <small className="table-subtext">{variance(job.actual_filament_weight_g, job.predicted_filament_weight_g)}</small> : null}</dd></div><div><dt>Actual filament cost</dt><dd className="print-result-emphasis">{currencyAmount(job.actual_filament_cost, job.cost_currency ?? 'USD')}{job.cost_currency_conflict ? <small className="table-subtext">Captured segment prices use different currencies and cannot be combined.</small> : !job.cost_complete && Number(job.unpriced_filament_weight_g) > 0 ? <small className="table-subtext">{grams(job.unpriced_filament_weight_g, 1)} has no compatible captured price</small> : null}</dd></div><div><dt>Object height / layers</dt><dd>{metadata.object_height ? `${compactNumber(metadata.object_height, 2)} mm` : '—'} / {metadata.layer_count ?? '—'}</dd></div><div><dt>G-code file size</dt><dd>{metadata.size ? `${compactNumber(Number(metadata.size) / 1_048_576, 2)} MB` : 'Unavailable'}</dd></div>{job.timelapse_url ? <div><dt>Timelapse</dt><dd><a className="button button--small" href={job.timelapse_url} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Open video</a></dd></div> : null}</dl></section>
      </div>
      <section className="inspection-panel"><div className="section-heading"><div><p className="eyebrow">G-code inspection</p><h3>{job.inspection_status === 'blocked' ? 'Block condition detected' : titleCase(job.inspection_status)}</h3></div><StatusPill status={job.inspection_status} /></div>{mismatches.map((mismatch) => <p key={mismatch.field} className="form-error"><AlertTriangle size={16} /> {mismatch.label}: G-code {mismatch.gcode_value}; profile {mismatch.profile_value}</p>)}{warnings.map((message) => <p key={message} className="warning-note"><AlertTriangle size={16} /> {message}</p>)}{job.inspection_status === 'blocked' && job.inspection.printer_gate !== 'active' ? <p className="form-error"><AlertTriangle size={16} /> This inspection result did not pause the printer because its sliced Cura start sequence did not enter the Filament Manager inspection gate. The sliced G-code must call FILAMENT_MANAGER_START_PRINT with the managed material GUID before it calls your unchanged Klipper START_PRINT macro; do not add this line inside START_PRINT.</p> : null}{!mismatches.length && !warnings.length ? <p className="success-note"><CheckCircle2 size={17} /> The inspected settings match the exact managed profile.</p> : null}</section>
      <section><p className="eyebrow">Material segments</p><div className="mobile-card-list mobile-card-list--always">{job.segments.length ? job.segments.map((segment) => <article className="mobile-data-card" key={segment.id}><strong>Segment {segment.segment_number} · {titleCase(segment.source)}</strong><span>Spool {snapshotLabel(segment.state_snapshot, 'spool', 'code')}</span><span>{grams(segment.actual_filament_weight_g, 1)} · {currencyAmount(segment.actual_filament_cost, segment.cost_currency ?? 'USD')}</span>{segment.cost_per_gram ? <small>{costPerGram(segment.cost_per_gram, segment.cost_currency ?? 'USD')} captured cost · {dateTime(segment.started_at)} – {dateTime(segment.ended_at)}</small> : <small>{dateTime(segment.started_at)} – {dateTime(segment.ended_at)}</small>}</article>) : <p className="muted">No exact segments were recoverable for this print.</p>}</div></section>
      {canAssess && job.status !== 'in_progress' ? <section><p className="eyebrow">Print outcome</p><PrintAssessmentForm job={job} onSaved={async () => { await queryClient.invalidateQueries({ queryKey: ['prints'] }); onClose() }} /></section> : null}
      {job.assessments.length ? <section><p className="eyebrow">Assessment history</p>{[...job.assessments].sort((left, right) => right.revision - left.revision).map((assessment) => <p key={assessment.id}><strong>{titleCase(assessment.rating)}</strong> · {assessment.defect_tags.map(titleCase).join(', ') || 'No defects'}<br /><small>{dateTime(assessment.created_at)}{assessment.notes ? ` · ${assessment.notes}` : ''}</small></p>)}</section> : null}
    </Modal>
  )
}

export default function PrintHistoryPage() {
  const { user } = useAuth()
  const [status, setStatus] = useState('')
  const [printerId, setPrinterId] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<PrintJobPage['per_page']>(10)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const query = useQuery({
    queryKey: ['prints', printerId, status, page, perPage],
    queryFn: () => apiFetch<PrintJobPage>(`/prints/page?page=${page}&per_page=${perPage}${printerId ? `&printer_id=${printerId}` : ''}${status ? `&print_status=${status}` : ''}`),
    refetchInterval: 15_000,
  })
  const jobs = useMemo(() => query.data?.items ?? [], [query.data?.items])
  const selectedSummary = jobs.find((job) => job.id === selectedId)
  const selected = useQuery({
    queryKey: ['prints', 'detail', selectedId],
    queryFn: () => apiFetch<PrintJob>(`/prints/${selectedId}`),
    enabled: selectedId !== null,
    staleTime: 30_000,
  })
  const currentPage = query.data?.page ?? page
  const totalPages = query.data?.total_pages ?? 1
  return <div>
    <PageHeader eyebrow="Canonical production record" title="Print history" description="Inspect each job against its exact profile, spool, nozzle, plate, slicer details, material segments, timelapse, and recorded outcome." />
    <section className="toolbar print-history-toolbar"><label className="select-field"><PrinterIcon size={17} /><select aria-label="Filter print history by printer" value={printerId} onChange={(event) => { setPrinterId(event.target.value); setPage(1) }}><option value="">All printers</option>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label><label className="select-field"><History size={17} /><select aria-label="Filter print outcomes" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}><option value="">All outcomes</option><option value="in_progress">In progress</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="cancelled">Cancelled</option><option value="legacy_unknown">Unknown print status</option></select></label><label className="select-field"><Rows3 size={17} /><span>Per page</span><select aria-label="Prints per page" value={perPage} onChange={(event) => { setPerPage(Number(event.target.value) as PrintJobPage['per_page']); setPage(1) }}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label><nav className="print-history-pagination" aria-label="Print history pages"><button className="button button--small" type="button" onClick={() => setPage(1)} disabled={currentPage <= 1}><ChevronFirst size={16} /> First</button><button className="button button--small" type="button" onClick={() => setPage(Math.max(1, currentPage - 1))} disabled={currentPage <= 1}><ChevronLeft size={16} /> Previous</button><button className="button button--small" type="button" onClick={() => setPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage >= totalPages}>Next <ChevronRight size={16} /></button><button className="button button--small" type="button" onClick={() => setPage(totalPages)} disabled={currentPage >= totalPages}>Last <ChevronLast size={16} /></button></nav><span className="toolbar__summary">{query.data ? pageSummary(query.data) : query.isError ? 'Print records unavailable' : 'Loading print records'}</span></section>
    {query.isLoading ? <LoadingState label="Loading print history" /> : query.isError ? <EmptyState icon={AlertTriangle} title="Print history unavailable" description={actionableApiError(query.error)} action={<button className="button" type="button" onClick={() => void query.refetch()}>Try again</button>} /> : !jobs.length ? <EmptyState icon={FileSearch} title="No print history yet" description="Moonraker history and new exact-state prints will appear here automatically." /> : <>
      <div className="table-card desktop-data-table"><table><thead><tr><th>Print</th><th>Material state</th><th>Inspection</th><th>Outcome</th><th>Started</th><th>Duration</th></tr></thead><tbody>{jobs.map((job) => <tr className={printOutcomeClass(job)} key={job.id} onClick={() => setSelectedId(job.id)} tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && setSelectedId(job.id)}><td><div className={`print-table-identity${job.thumbnail_url ? '' : ' print-table-identity--without-thumbnail'}`}>{job.thumbnail_url ? <img className="print-table-thumbnail" src={job.thumbnail_url} alt="" /> : null}<span><strong>{job.filename}</strong><small className="table-subtext">{job.slicer ?? titleCase(job.source)}</small></span></div></td><td>{historicalMaterialLabel(job)}<small className="table-subtext">{job.actual_filament_weight_g ? `${grams(job.actual_filament_weight_g, 1)} · ${currencyAmount(job.actual_filament_cost, job.cost_currency ?? 'USD')}` : job.material_profile_id ? 'Exact saved profile' : 'No exact profile'}</small></td><td><StatusPill status={job.inspection_status} /></td><td><StatusPill status={printOutcome(job)} /></td><td>{dateTime(job.started_at)}</td><td>{job.print_duration_seconds ? `${Math.round(Number(job.print_duration_seconds) / 60)} min` : '—'}</td></tr>)}</tbody></table></div>
      <div className="mobile-card-list">{jobs.map((job) => <button className={`mobile-data-card mobile-data-card--button ${printOutcomeClass(job)}`.trim()} key={job.id} onClick={() => setSelectedId(job.id)}>{job.thumbnail_url ? <img className="print-card-thumbnail" src={job.thumbnail_url} alt="" /> : null}<span className="mobile-data-card__heading"><strong>{job.filename}</strong><StatusPill status={job.inspection_status} /></span><span>{job.state_snapshot.legacy_unresolved === true ? 'Legacy record · exact material state unavailable' : `${historicalMaterialLabel(job)} · ${job.actual_filament_weight_g ? `${grams(job.actual_filament_weight_g, 1)} · ${currencyAmount(job.actual_filament_cost, job.cost_currency ?? 'USD')}` : job.material_profile_id ? 'exact saved profile' : 'no exact profile'}`}</span><span>Outcome: {titleCase(printOutcome(job))}</span><small><Clock3 size={14} /> {dateTime(job.started_at)}</small></button>)}</div>
    </>}
    {selectedId && selected.isPending ? <Modal title={selectedSummary?.filename ?? 'Print details'} description="Loading the immutable print record." onClose={() => setSelectedId(null)}><LoadingState label="Loading print details" /></Modal> : null}
    {selectedId && selected.isError ? <Modal title={selectedSummary?.filename ?? 'Print details'} description="The immutable print record could not be loaded." onClose={() => setSelectedId(null)} footer={<><button className="button" type="button" onClick={() => setSelectedId(null)}>Close</button><button className="button button--primary" type="button" onClick={() => void selected.refetch()}>Try again</button></>}><p className="form-error" role="alert"><AlertTriangle size={16} /> {actionableApiError(selected.error)}</p></Modal> : null}
    {selected.data ? <PrintDetail job={selected.data} canAssess={user?.role !== 'viewer'} onClose={() => setSelectedId(null)} /> : null}
  </div>
}
