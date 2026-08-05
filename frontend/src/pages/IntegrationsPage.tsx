import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseZap, FileSpreadsheet, RefreshCw, RotateCcw, Unplug } from 'lucide-react'
import { apiFetch } from '../api/client'
import type { IntegrationStatus, OutboxJob } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime, titleCase } from '../lib/format'

export default function IntegrationsPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const statuses = useQuery({ queryKey: ['integration-status'], queryFn: () => apiFetch<IntegrationStatus[]>('/integrations/status'), refetchInterval: 30_000 })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => apiFetch<OutboxJob[]>('/jobs?limit=100'), refetchInterval: 10_000 })
  const action = useMutation({ mutationFn: (path: string) => apiFetch(path, { method: 'POST' }), onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ['jobs'] }), client.invalidateQueries({ queryKey: ['integration-status'] })]) } })
  const retry = useMutation({ mutationFn: (id: string) => apiFetch(`/jobs/${id}/retry`, { method: 'POST' }), onSuccess: () => client.invalidateQueries({ queryKey: ['jobs'] }) })
  const canOperate = user?.role !== 'viewer'
  return <div><PageHeader eyebrow="External projections" title="Integrations" description="Filament Manager remains authoritative while Spoolman, Moonraker, and Google Sheets receive supported projections." actions={<button className="button" onClick={() => void statuses.refetch()}><RefreshCw size={16} /> Check now</button>} />{statuses.isLoading ? <LoadingState label="Checking services" /> : <section className="integration-grid">{statuses.data?.map((item) => <article className="integration-card" key={item.service}><span className="integration-card__icon">{item.service.startsWith('Spoolman') ? <DatabaseZap size={23} /> : item.service.startsWith('Google') ? <FileSpreadsheet size={23} /> : <Unplug size={23} />}</span><div><h2>{item.service}</h2><p>{item.detail}</p><small>Checked {dateTime(item.checked_at)}</small></div><StatusPill status={item.status} />{canOperate && item.service === 'Spoolman' && <button className="button" onClick={() => action.mutate('/integrations/spoolman/reconcile')}>Queue reconciliation</button>}{canOperate && item.service === 'Google Sheets' && <button className="button" onClick={() => action.mutate('/integrations/google/publish')}>Publish pending</button>}</article>)}</section>}<section className="section-heading"><div><p className="eyebrow">Durable delivery</p><h2>Projection jobs</h2></div></section>{jobs.isLoading ? <LoadingState /> : !jobs.data?.length ? <EmptyState icon={RefreshCw} title="No jobs recorded" description="Projection work appears here after inventory, measurements, plates, or profiles change." /> : <div className="table-card"><table><thead><tr><th>Job</th><th>Aggregate</th><th>Status</th><th>Attempts</th><th>Created</th><th>Completed</th><th /></tr></thead><tbody>{jobs.data.map((job) => <tr key={job.id}><td><strong>{titleCase(job.job_type.replaceAll('.', ' '))}</strong></td><td>{titleCase(job.aggregate_type)}</td><td><StatusPill status={job.status} /></td><td>{job.attempts}</td><td>{dateTime(job.created_at)}</td><td>{dateTime(job.completed_at)}</td><td>{user?.role === 'administrator' && ['failed', 'dead'].includes(job.status) && <button className="icon-button" onClick={() => retry.mutate(job.id)} title="Retry job"><RotateCcw size={17} /></button>}</td></tr>)}</tbody></table></div>}{action.isError && <p className="form-error">{action.error.message}</p>}</div>
}
