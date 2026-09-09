import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import { dateTime } from '../lib/format'

type Activity = { last_completed_print_at: string | null; last_other_print_at: string | null }

/** One shared query per entity kind, including exact material-change attribution. */
export function PrintActivityDates({ kind, id }: { kind: 'filament' | 'spool' | 'printer' | 'nozzle' | 'plate' | 'side'; id: string }) {
  const query = useQuery({ queryKey: ['print-activity', kind], queryFn: () => apiFetch<Record<string, Activity>>(`/prints/activity/${kind}`), staleTime: 30_000, refetchInterval: 60_000 })
  const activity = query.data?.[id]
  const value = (date: string | null | undefined) => query.isPending ? 'Loading…' : query.isError ? 'Unable to load' : date ? dateTime(date) : 'No recorded print'
  return <dl className="definition-list definition-list--compact print-activity-dates">
    <div><dt>Last completed print</dt><dd>{value(activity?.last_completed_print_at)}</dd></div>
    <div><dt>Last other print</dt><dd>{value(activity?.last_other_print_at)}</dd></div>
  </dl>
}
