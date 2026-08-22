import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Database, Download, ExternalLink, RefreshCw, RotateCcw, ShieldCheck, TriangleAlert } from 'lucide-react'
import { apiFetch } from '../api/client'
import type { DiagnosticCheck, DiagnosticOverview, DiagnosticRun, OutboxJob, ProjectionRebuildResult, VersionStatus } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime, titleCase } from '../lib/format'

const categories = [
  { key: 'connection', title: 'Connections', description: 'Sanitized reachability and schema checks.' },
  { key: 'synchronization', title: 'Synchronizations', description: 'Printer and Cura freshness without exposing credentials.' },
  { key: 'worker', title: 'Workers and queues', description: 'Scheduler, dispatcher, and durable delivery health.' },
  { key: 'operational', title: 'Operational state', description: 'Other conditions that need operator awareness.' },
]

function CheckGrid({ checks }: { checks: DiagnosticCheck[] }) {
  return <div className="diagnostic-check-grid">{checks.map((check) => <article className="diagnostic-check" key={check.key}>
    <div><strong>{check.label}</strong><p>{check.detail}</p><small>Checked {dateTime(check.checked_at)}</small></div>
    <StatusPill status={check.status} />
  </article>)}</div>
}

export default function DiagnosticsPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const overview = useQuery({ queryKey: ['diagnostics'], queryFn: () => apiFetch<DiagnosticOverview>('/diagnostics'), refetchInterval: 30_000 })
  const version = useQuery({ queryKey: ['diagnostics-version'], queryFn: () => apiFetch<VersionStatus>('/diagnostics/version'), staleTime: 15 * 60_000 })
  const runs = useQuery({ queryKey: ['diagnostic-runs'], queryFn: () => apiFetch<DiagnosticRun[]>('/diagnostics/validation-runs') })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => apiFetch<OutboxJob[]>('/jobs?limit=100'), refetchInterval: 10_000 })
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ['diagnostics'] }), client.invalidateQueries({ queryKey: ['diagnostics-version'] }), client.invalidateQueries({ queryKey: ['diagnostic-runs'] }), client.invalidateQueries({ queryKey: ['jobs'] })]) }
  const validation = useMutation({ mutationFn: () => apiFetch<DiagnosticRun>('/diagnostics/validation-runs', { method: 'POST' }), onSuccess: refresh })
  const rebuild = useMutation({
    mutationFn: () => apiFetch<ProjectionRebuildResult>('/diagnostics/projection-rebuild', { method: 'POST' }),
    onSuccess: refresh,
  })
  const action = useMutation({ mutationFn: (path: string) => apiFetch(path, { method: 'POST' }), onSuccess: refresh })
  const retry = useMutation({ mutationFn: (id: string) => apiFetch(`/jobs/${id}/retry`, { method: 'POST' }), onSuccess: refresh })
  const canOperate = user?.role !== 'viewer'
  const isAdministrator = user?.role === 'administrator'
  const latestRun = validation.data ?? runs.data?.[0]
  const error = validation.error ?? rebuild.error ?? action.error ?? retry.error

  return <div>
    <PageHeader eyebrow="Operations and recovery" title="Diagnostics" description="Connection, synchronization, worker, queue, validation, and bounded error information in one place." actions={<button className="button" onClick={() => void refresh()} disabled={overview.isFetching || version.isFetching}><RefreshCw size={16} /> Check now</button>} />
    <section className="card diagnostic-version">
      <div><p className="eyebrow">Application version</p><h2>Filament Manager {version.data?.running_version ? `v${version.data.running_version}` : ''}</h2><p>{version.data?.detail ?? (version.isLoading ? 'Checking the latest published GitHub release…' : 'Version information is unavailable.')}</p></div>
      {version.data ? <div className="diagnostic-version__status"><StatusPill status={version.data.status === 'current' ? 'healthy' : version.data.status === 'update_available' ? 'warning' : version.data.status} label={titleCase(version.data.status)} /><span>Latest: {version.data.latest_version ? `v${version.data.latest_version}` : 'Unavailable'}</span>{version.data.release_url ? <a className="button" href={version.data.release_url} target="_blank" rel="noreferrer">View release <ExternalLink size={15} /></a> : null}</div> : null}
    </section>
    <section className="diagnostic-actions card">
      <div><p className="eyebrow">Recovery readiness</p><h2><ShieldCheck size={20} /> Backup and restore validation</h2><p>Runs read-only schema, immutable-history, credential-hash, projection, Cura synchronization, connection, and worker checks. It does not restore or overwrite the live database.</p></div>
      <div className="detail-actions">
        {isAdministrator ? <button className="button button--primary" disabled={validation.isPending} onClick={() => validation.mutate()}>{validation.isPending ? 'Validating…' : 'Run validation'}</button> : <span className="muted">Administrator access is required to run validation.</span>}
        {isAdministrator ? <button className="button" disabled={rebuild.isPending} onClick={() => { if (window.confirm('Queue a safe rebuild of Spoolman, Google, and managed Cura projections from canonical Filament Manager data?')) rebuild.mutate() }}><Database size={16} />{rebuild.isPending ? 'Queuing…' : 'Rebuild projections'}</button> : null}
      </div>
      {rebuild.data ? <p className="deployment-note" role="status">Queued {rebuild.data.queued_jobs} rebuild job{rebuild.data.queued_jobs === 1 ? '' : 's'}.</p> : null}
      {latestRun ? <div className="validation-result">
        <div className="section-heading"><div><p className="eyebrow">Latest validation</p><h3>{dateTime(latestRun.started_at)}</h3></div><StatusPill status={latestRun.status} /></div>
        {latestRun.results.error ? <p className="form-error">{latestRun.results.error}</p> : null}
        {latestRun.results.summary ? <div className="metric-grid metric-grid--compact">{Object.entries(latestRun.results.summary).map(([key, value]) => <article className="metric-card" key={key}><span>{titleCase(key)}</span><strong>{value}</strong></article>)}</div> : null}
        {latestRun.results.checks?.length ? <CheckGrid checks={latestRun.results.checks.filter((check) => check.category === 'recovery')} /> : null}
      </div> : <p className="muted">No recovery validation has been recorded yet.</p>}
    </section>
    {error ? <p className="form-error" role="alert">{error.message}</p> : null}
    {overview.isLoading ? <LoadingState label="Checking operations" /> : overview.error ? <p className="form-error">{overview.error.message}</p> : <>
      {categories.map((category) => {
        const checks = overview.data?.checks.filter((check) => check.category === category.key) ?? []
        return <section key={category.key}><div className="section-heading"><div><p className="eyebrow">Live diagnostics</p><h2>{category.title}</h2><p>{category.description}</p></div></div>{checks.length ? <CheckGrid checks={checks} /> : <p className="muted">No checks reported in this category.</p>}</section>
      })}
      <section><div className="section-heading"><div><p className="eyebrow">Durable delivery</p><h2>Queue summary</h2></div></div><div className="metric-grid metric-grid--compact">{Object.entries(overview.data?.queue_counts ?? {}).map(([key, value]) => <article className="metric-card" key={key}><span>{titleCase(key)}</span><strong>{value}</strong></article>)}</div>{Object.keys(overview.data?.job_type_counts ?? {}).length ? <div className="tag-list">{Object.entries(overview.data?.job_type_counts ?? {}).map(([key, value]) => <span className="tag" key={key}>{titleCase(key.replaceAll('.', ' '))}: {value}</span>)}</div> : null}</section>
      {overview.data?.failure_groups?.length ? <section><div className="section-heading"><div><p className="eyebrow">Actionable projection failures</p><h2><TriangleAlert size={20} /> Latest cause by job type</h2><p>One sanitized representative is always retained for every failing projection type, even when newer errors would otherwise push it out of the recent log.</p></div></div><div className="mobile-card-list mobile-card-list--always">{overview.data.failure_groups.map((failure) => <article className="mobile-data-card" key={failure.job_type}><div><strong>{titleCase(failure.job_type.replaceAll('.', ' '))}</strong><StatusPill status={failure.status} /></div><span>{failure.count} actionable · attempt {failure.attempts} of {failure.max_attempts} · {failure.error_class}</span><small>{failure.detail ?? 'No additional detail retained.'} Last failure {dateTime(failure.occurred_at)}.</small></article>)}</div></section> : null}
      <section><div className="section-heading"><div><p className="eyebrow">Bounded operational log</p><h2><TriangleAlert size={20} /> Recent errors</h2></div><a className="button" href="/api/v1/diagnostics/log.txt"><Download size={16} /> Download log</a></div>{overview.data?.error_log.length ? <div className="mobile-card-list mobile-card-list--always">{overview.data.error_log.map((entry, index) => <article className="mobile-data-card" key={`${entry.source}-${entry.occurred_at}-${index}`}><div><strong>{entry.summary}</strong><StatusPill status={entry.severity} /></div><span>{entry.source} · {dateTime(entry.occurred_at)}</span><small>{entry.detail ?? 'No additional detail retained.'}</small></article>)}</div> : <EmptyState icon={Activity} title="No recent operational errors" description="Failed projections, Cura synchronization, and active error notifications appear here without external response bodies." />}</section>
    </>}
    <section><div className="section-heading"><div><p className="eyebrow">Projection operations</p><h2>Recent jobs</h2></div>{canOperate ? <div className="detail-actions"><button className="button" disabled={action.isPending} onClick={() => action.mutate('/integrations/spoolman/reconcile')}>Queue Spoolman reconciliation</button><button className="button" disabled={action.isPending} onClick={() => action.mutate('/integrations/google/publish')}>Publish pending Google updates</button></div> : null}</div>{jobs.isLoading ? <LoadingState /> : !jobs.data?.length ? <EmptyState icon={RefreshCw} title="No jobs recorded" description="Projection work appears here after canonical records change." /> : <div className="table-card"><table><thead><tr><th>Job</th><th>Aggregate</th><th>Status</th><th>Attempts</th><th>Latest failure</th><th>Created</th><th>Completed</th><th /></tr></thead><tbody>{jobs.data.map((job) => <tr key={job.id}><td><strong>{titleCase(job.job_type.replaceAll('.', ' '))}</strong></td><td>{titleCase(job.aggregate_type)}</td><td><StatusPill status={job.status} /></td><td>{job.attempts}</td><td>{job.last_error_class ? `${job.last_error_class} · ${dateTime(job.last_error_at)}` : '—'}</td><td>{dateTime(job.created_at)}</td><td>{dateTime(job.completed_at)}</td><td>{isAdministrator && ['failed', 'dead'].includes(job.status) ? <button className="icon-button" onClick={() => retry.mutate(job.id)} title="Retry job"><RotateCcw size={17} /></button> : null}</td></tr>)}</tbody></table></div>}</section>
  </div>
}
