import { useQuery } from '@tanstack/react-query'
import { Activity, Search } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { AuditEvent } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { dateTime, titleCase } from '../lib/format'

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
  const query = useQuery({ queryKey: ['audit'], queryFn: () => apiFetch<AuditEvent[]>('/audit-events?limit=200') })
  const events = query.data?.filter((event) => `${event.action} ${event.object_type} ${event.source}`.toLowerCase().includes(search.toLowerCase())) ?? []
  return <div><PageHeader eyebrow="Immutable history" title="Activity" description="Security and operational events from browser actions, imports, workers, and integrations." /><section className="toolbar"><label className="search-field"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter actions and object types" /></label><span className="toolbar__summary">{events.length} events</span></section>{query.isLoading ? <LoadingState /> : !events.length ? <EmptyState icon={Activity} title="No activity found" description="Recorded changes and sign-ins appear here." /> : <ol className="timeline">{events.map((event) => { const tone = activityTone(event.action); return <li className={`timeline--${tone}`} key={event.id}><span className="timeline__marker" /><article><header><strong>{titleCase(event.action.replaceAll('.', ' '))}</strong><span className={`activity-tone activity-tone--${tone}`}>{titleCase(tone)}</span><span>{dateTime(event.occurred_at)}</span></header><p>{titleCase(event.object_type)} · {event.source}</p><small>Correlation {event.correlation_id}</small></article></li> })}</ol>}</div>
}
