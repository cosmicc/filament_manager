import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { AlertTriangle, ArrowRight, Boxes, ChevronLeft, ChevronRight, FlaskConical, Gauge, Layers3, PackageOpen, Palette, Plus, Printer, RefreshCw, Scale, Thermometer, WifiOff } from 'lucide-react'
import { apiFetch } from '../api/client'
import type { DashboardData } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { PrintThumbnail } from '../components/PrintThumbnail'
import { StatusPill } from '../components/StatusPill'
import { Link } from '../context/RouterContext'
import { useAuth } from '../context/AuthContext'
import { filamentSwatchStyle } from '../lib/colors'
import { compactNumber, currencyAmount, dateTime, grams, percent, titleCase } from '../lib/format'
import { materialIdentitySummary } from '../lib/materialIdentity'

function temperatureSummary(current: string | null, target: string | null) {
  if (current == null) return 'Not reported'
  const currentText = `${compactNumber(current, 0)} °C`
  return target != null && Number(target) > 0
    ? `${currentText} / ${compactNumber(target, 0)} °C target`
    : currentText
}

function duration(value: string | null) {
  if (value == null) return '—'
  const totalMinutes = Math.max(0, Math.round(Number(value) / 60))
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours ? `${hours} hr ${minutes} min` : `${minutes} min`
}

function MetricCard({ icon: Icon, label, value, detail, tone = '' }: {
  icon: typeof Boxes
  label: string
  value: number
  detail: string
  tone?: string
}) {
  return (
    <article className={`metric-card ${tone}`} title={`${label}: ${value} · ${detail}`}>
      <span className="metric-card__icon"><Icon size={20} /></span>
      <div><p>{label}</p><strong>{value}</strong><small>{detail}</small></div>
    </article>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const sync = useMutation({
    mutationFn: (printerId: string) => apiFetch<{ queued: number }>(`/printers/${printerId}/sync-cura`, { method: 'POST' }),
  })
  const query = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => apiFetch<DashboardData>('/dashboard'),
    refetchInterval: 10_000,
    refetchOnReconnect: 'always',
    refetchOnWindowFocus: 'always',
  })
  if (query.isLoading) return <LoadingState label="Loading workshop status" />
  if (!query.data) return <EmptyState icon={AlertTriangle} title="Dashboard unavailable" description="The operational overview could not be loaded. Check the application service and try again." action={<button className="button" onClick={() => void query.refetch()}>Try again</button>} />
  const contexts = query.data.printer_contexts ?? []
  const selected = contexts.find((context) => context.printer_id === selectedId) ?? contexts[0]
  const selectedIndex = selected ? contexts.indexOf(selected) : 0
  const data = selected ? { ...query.data, ...selected, active_spool: selected.active_spools[0] ?? null } : query.data
  const activeSpools = selected?.active_spools ?? (data.active_spool ? [data.active_spool] : [])
  const selectPrinter = (id: string) => { setSelectedId(id); sync.reset() }
  const movePrinter = (offset: number) => selectPrinter(contexts[(selectedIndex + offset + contexts.length) % contexts.length].printer_id)
  return (
    <div className="dashboard-page">
      <PageHeader eyebrow="Workshop overview" title="Dashboard" actions={<>
        <Link to="/spools?action=weigh" className="button button--primary"><Scale size={17} /> Weigh spool</Link>
        <Link to={selected ? `/plates?printer_id=${selected.printer_id}` : '/plates'} className="button"><Layers3 size={17} /> Build plate</Link>
        <Link to="/calibration" className="button"><FlaskConical size={17} /> Calibrate</Link>
        <Link to="/filaments/new" className="button"><PackageOpen size={17} /> Add filament</Link>
        <Link to="/spools?create=1" className="button"><Plus size={17} /> Add spool</Link>
        <Link to={`/spools?action=load${selected ? `&printer_id=${selected.printer_id}` : ''}`} className="button"><Boxes size={17} /> Load spool</Link>
        {user?.role === 'administrator' && <button className="button" disabled={!selected || sync.isPending} onClick={() => selected && sync.mutate(selected.printer_id)}><RefreshCw size={17} />{sync.isPending ? 'Queueing…' : 'Sync to Cura'}</button>}
      </>} />
      {sync.isSuccess && <p className="deployment-note" role="status">Settings queued for {sync.data.queued} matching Cura workstation(s). Close Cura and wait for synchronization to succeed before reopening.</p>}
      {sync.error && <p className="form-error" role="alert">{sync.error.message}</p>}
      <section className="dashboard-grid">
        <article className={`card printer-state-card printer-state-card--${data.printer_state.operational_status}`}>
          <header className={`printer-state-card__header${contexts.length > 1 ? ' printer-state-card__header--carousel' : ''}`}>
            {contexts.length > 1 && <button className="button button--icon" aria-label="Previous printer" onClick={() => movePrinter(-1)}><ChevronLeft size={22} /></button>}
            <span className="printer-state-card__icon"><Printer size={30} /></span>
            <div>
              <p className="eyebrow">Live Moonraker status</p>
              <h2>{data.printer_state.printer_name}</h2>
              <p>{data.printer_state.connection_status === 'connected'
                ? `Moonraker connected · Klipper ${data.printer_state.klipper_state ?? 'state unavailable'}`
                : data.printer_state.connection_status === 'not_configured'
                  ? 'No Moonraker printer is configured.'
                  : 'Moonraker is unavailable; printer power and network state cannot be confirmed.'}</p>
            </div>
            <StatusPill status={data.printer_state.operational_status} label={titleCase(data.printer_state.operational_status)} />
            {contexts.length > 1 && <button className="button button--icon" aria-label="Next printer" onClick={() => movePrinter(1)}><ChevronRight size={22} /></button>}
          </header>
          {data.printer_state.connection_status === 'connected' ? <div className={`printer-state-card__body${data.printer_state.operational_status === 'printing' ? ' printer-state-card__body--printing' : ''}`}>
            <section className={`printer-current-print${data.printer_state.thumbnail_url ? '' : ' printer-current-print--without-thumbnail'}`} aria-label="Current print state">
              {data.printer_state.thumbnail_url ? <PrintThumbnail className="printer-current-print__thumbnail" src={data.printer_state.thumbnail_url} alt={`Preview of ${data.printer_state.filename ?? 'current print'}`} /> : null}
              <div className="printer-current-print__content">
                <div className="printer-job-state">
                  <span><Gauge size={21} /></span>
                  <div><small>Printer state</small><strong>{titleCase(data.printer_state.operational_status)}</strong>{data.printer_state.filename ? <p title={data.printer_state.filename}>{data.printer_state.filename}</p> : null}</div>
                  {data.printer_state.progress_percent != null ? <strong className="printer-job-state__percent">{percent(data.printer_state.progress_percent)}</strong> : null}
                  {data.printer_state.progress_percent != null ? <div className="progress"><span style={{ width: `${Math.min(100, Math.max(0, Number(data.printer_state.progress_percent)))}%` }} /></div> : null}
                </div>
                {data.printer_state.print_job_id ? <dl className="printer-live-stats">
                  <div><dt>Elapsed</dt><dd>{duration(data.printer_state.print_duration_seconds)}</dd></div>
                  <div><dt>Estimated</dt><dd>{duration(data.printer_state.estimated_duration_seconds)}</dd></div>
                  <div><dt>Filament used</dt><dd>{grams(data.printer_state.actual_filament_weight_g, 1)}</dd></div>
                  <div><dt>Cost so far</dt><dd>{currencyAmount(data.printer_state.actual_filament_cost, data.printer_state.cost_currency ?? 'USD')}</dd></div>
                </dl> : null}
              </div>
            </section>
            <section className="printer-temperature-grid" aria-label="Live printer temperatures">
              <div><span><Thermometer size={18} /></span><small>Nozzle</small><strong>{temperatureSummary(data.printer_state.nozzle_temperature_c, data.printer_state.nozzle_target_c)}</strong></div>
              <div><span><Thermometer size={18} /></span><small>Bed</small><strong>{temperatureSummary(data.printer_state.bed_temperature_c, data.printer_state.bed_target_c)}</strong></div>
              <div><span><Thermometer size={18} /></span><small>Chamber</small><strong>{temperatureSummary(data.printer_state.chamber_temperature_c, data.printer_state.chamber_target_c)}</strong></div>
            </section>
          </div> : <div className="printer-state-card__unavailable"><WifiOff size={24} /><span><strong>Live printer telemetry is unavailable</strong><small>The dashboard will retry automatically every 10 seconds.</small></span></div>}
          <footer>Checked {dateTime(data.printer_state.checked_at)}{data.printer_state.idle_state ? ` · Idle controller: ${data.printer_state.idle_state}` : ''}{data.printer_state.power_off_remaining_seconds != null ? ` · Power-off countdown: ${duration(data.printer_state.power_off_remaining_seconds)} remaining if idle` : data.printer_state.idle_timeout_seconds ? ` · Idle timeout: ${duration(data.printer_state.idle_timeout_seconds)}` : ''}</footer>
        </article>

        <article className="card active-spool-card">
          <header className="card__header"><div><p className="eyebrow">Printing context</p><h2>Active {activeSpools.length > 1 ? "spools" : "spool"}</h2></div></header>
          {activeSpools.length ? activeSpools.map((spool) => (
            <div className="active-spool" key={spool.id}>
              <span className="filament-swatch filament-swatch--large" style={filamentSwatchStyle(spool.color_mode, spool.color_hexes, spool.color_hex ?? '2F80A5')} />
              <div className="active-spool__identity"><small>{spool.active_extruder ?? "extruder"}</small><strong>{spool.spool_code}</strong><span>{[spool.vendor_name, materialIdentitySummary(spool)].filter(Boolean).join(' · ')}</span></div>
              <div className="remaining-visual"><div className="remaining-visual__labels"><span>{grams(spool.remaining_mass_effective_g)}</span><strong>{percent(spool.remaining_percent)}</strong></div><div className="progress"><span style={{ width: `${Math.min(100, Number(spool.remaining_percent))}%` }} /></div><small>{spool.weight_confidence} confidence</small></div>
              <Link className="text-link" to="/spools">View inventory <ArrowRight size={15} /></Link>
            </div>
          )) : <EmptyState icon={Boxes} title="No active spool" description="Load a spool through Inventory or the confirmed Fluidd workflow. The current physical spool updates automatically." action={<Link className="button" to="/spools">Open inventory</Link>} />}
        </article>

        <article className="card plate-card">
          <header className="card__header"><div><p className="eyebrow">Printer surface</p><h2>Active build plate</h2></div><Layers3 size={21} /></header>
          {data.active_plate ? <div className="plate-summary"><div className={`plate-illustration${data.active_plate.image_url ? ' plate-illustration--photo' : ''}`}>{data.active_plate.image_url ? <img src={data.active_plate.image_url} alt={`${data.active_plate.display_name} build plate`} /> : null}<span>{data.active_plate_surface?.surface_code ?? data.active_plate.plate_code}</span></div><strong>{data.active_plate.display_name}</strong><span>{data.active_plate_surface ? `Side ${data.active_plate_surface.side.toUpperCase()} · ${data.active_plate_surface.surface_material ?? 'Surface not specified'}` : 'Side not selected'}</span><StatusPill status={data.active_plate.condition} /></div> : <EmptyState icon={Layers3} title="No plate selected" description="Select a synchronized P-number plate side for a configured printer." action={<Link className="button" to="/plates">Open plates</Link>} />}
        </article>

        {contexts.length > 1 && <section className="card printer-overview" aria-label="All printers">
          <header className="card__header"><h2>All printers</h2><span className="muted">Select a printer to view its details</span></header>
          <div className="table-scroll"><table><thead><tr><th>Printer</th><th>Status</th><th>Loaded spools</th><th>Build plate</th></tr></thead><tbody>
            {contexts.map((context) => <tr key={context.printer_id}>
              <td><button className="button" aria-pressed={selected?.printer_id === context.printer_id} onClick={() => selectPrinter(context.printer_id)}>{context.printer_state.printer_name}</button></td>
              <td><StatusPill status={context.printer_state.operational_status} /></td>
              <td>{context.active_spools.length ? context.active_spools.map((spool) => <div key={spool.id}>{spool.active_extruder ?? 'extruder'} · {spool.spool_code} · {materialIdentitySummary(spool)}</div>) : 'No spool loaded'}</td>
              <td>{context.active_plate ? `${context.active_plate_surface?.surface_code ?? context.active_plate.plate_code} · ${context.active_plate.display_name}` : 'No plate selected'}</td>
            </tr>)}
          </tbody></table></div>
        </section>}
        <section className="metric-grid dashboard-metric-grid" aria-label="Inventory summary">
          <MetricCard icon={Boxes} label="Total spools" value={data.total_spools} detail="Active inventory" />
          <MetricCard icon={Scale} label="Needs weighing" value={data.needs_weighing} detail="Manual check" tone={data.needs_weighing ? 'metric-card--warning' : ''} />
          <MetricCard icon={AlertTriangle} label="Low or empty" value={data.low_spools + data.empty_spools} detail={`${data.empty_spools} empty`} tone={data.low_spools + data.empty_spools ? 'metric-card--warning' : ''} />
          <MetricCard icon={Palette} label="Colors" value={data.distinct_colors} detail="Named colors" tone="metric-card--accent" />
          {Object.entries(data.material_spool_counts).map(([material, count]) => <MetricCard key={material} icon={PackageOpen} label={material} value={count} detail={count === 1 ? 'spool' : 'spools'} tone="metric-card--material" />)}
        </section>


      </section>
    </div>
  )
}
