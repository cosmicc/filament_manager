import { useQuery } from '@tanstack/react-query'
import { Activity, Search } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { AuditEvent } from '../api/types'
import { DateWithAge } from '../components/DateWithAge'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { titleCase } from '../lib/format'

type ActivityTone = 'success' | 'error' | 'warning' | 'info' | 'security'

function activityTone(action: string): ActivityTone {
  const normalized = action.toLowerCase()
  if (/failed|error|reject|denied|invalid/.test(normalized)) return 'error'
  if (/cancel|retire|deactivate|clear|reset|retry|override/.test(normalized)) return 'warning'
  if (/login|logout|password|pair|revoke/.test(normalized)) return 'security'
  if (/create|complete|publish|apply|save|update|install|select|measure|succeed/.test(normalized)) return 'success'
  return 'info'
}

export default function ActivityPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const query = useQuery({ queryKey: ['audit', page, perPage, search], queryFn: () => apiFetch<{ items: AuditEvent[]; page: number; pages: number; total: number }>(`/audit-events/page?page=${page}&per_page=${perPage}&search=${encodeURIComponent(search)}`) })
  const events = query.data?.items ?? []
  return <div><PageHeader eyebrow="Immutable history" title="Activity" description="Security and operational events from browser actions, imports, workers, and integrations." /><section className="toolbar"><label className="search-field"><Search size={18} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Filter actions and object types" /></label><label>Events per page<select value={perPage} onChange={(event) => { setPerPage(Number(event.target.value)); setPage(1) }}>{[20, 50, 100, 200].map((size) => <option key={size}>{size}</option>)}</select></label><span className="toolbar__summary">{query.data?.total ?? 0} events</span></section>{query.isError ? <p className="form-error" role="alert">{query.error.message}</p> : query.isLoading ? <LoadingState /> : !events.length ? <EmptyState icon={Activity} title="No activity found" description="Recorded changes and sign-ins appear here." /> : <ol className="timeline">{events.map((event) => { const tone = activityTone(event.action); return <li className={`timeline--${tone}`} key={event.id}><span className="timeline__marker" /><article><header><strong>{titleCase(event.action.replaceAll('.', ' '))}</strong><span className={`activity-tone activity-tone--${tone}`}>{titleCase(tone)}</span><span><DateWithAge value={event.occurred_at} /></span></header><p>{titleCase(event.object_type)} · {event.source}</p><small>Correlation {event.correlation_id}</small></article></li> })}</ol>}{query.data && <nav className="toolbar" aria-label="Activity pagination"><button className="button" disabled={query.data.page <= 1} onClick={() => setPage(1)}>First</button><button className="button" disabled={query.data.page <= 1} onClick={() => setPage(query.data!.page - 1)}>Previous</button><span>Page {query.data.page} of {query.data.pages}</span><button className="button" disabled={query.data.page >= query.data.pages} onClick={() => setPage(query.data!.page + 1)}>Next</button><button className="button" disabled={query.data.page >= query.data.pages} onClick={() => setPage(query.data!.pages)}>Last</button></nav>}</div>
}
