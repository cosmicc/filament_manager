import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import type { BuildPlate } from '../api/types'
import { EditorSection } from './EditorSection'

type Ratings = { template_id: string; record_version: number; ratings: Record<string, number>; printer_name?: string; active_side_id?: string | null }

export function ratingLabel(rating: number | undefined) {
  return rating == null ? 'Unrated' : rating === 0 ? '0 stars · Avoid — may damage plate' : `${'★'.repeat(rating)}${'☆'.repeat(5 - rating)}${rating === 5 ? ' · Recommended' : ''}`
}

/** Rating changes are individually saved and version checked, outside print settings. */
export function PlateRatingEditor({ templateId, plates }: { templateId: string; plates: BuildPlate[] }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['plate-ratings', templateId], queryFn: () => apiFetch<Ratings>(`/build-plate-ratings/${templateId}`) })
  const save = useMutation({ mutationFn: ({ side, value }: { side: string; value: string }) => {
    const ratings = { ...query.data!.ratings }
    if (value === '') delete ratings[side]; else ratings[side] = Number(value)
    return apiFetch<Ratings>(`/build-plate-ratings/${templateId}`, { method: 'PUT', body: JSON.stringify({ expected_version: query.data!.record_version, ratings }) })
  }, onSuccess: (data) => { client.setQueryData(['plate-ratings', templateId], data); void client.invalidateQueries({ queryKey: ['plate-compatibility'] }) } })
  return <div className="template-rating-section"><EditorSection title="Build plate compatibility" description="Ratings save immediately. Zero stars blocks printing; unrated sides remain allowed."><div className="form-grid">{plates.flatMap((plate) => plate.surfaces.map((side) => <label key={side.id}>{side.surface_code} · {plate.display_name} · Side {side.side.toUpperCase()}<select aria-label={`Rating for ${side.surface_code}`} value={query.data?.ratings[side.id] ?? ''} disabled={!query.data || save.isPending} onChange={(event) => save.mutate({ side: side.id, value: event.target.value })}><option value="">Unrated</option>{[0, 1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{ratingLabel(value)}</option>)}</select></label>))}</div>{(query.error || save.error) && <p className="form-error" role="alert">{(query.error || save.error)?.message}</p>}</EditorSection></div>
}

/** Recommendations follow each current template and preserve unknown compatibility. */
export function PlateCompatibility({ filamentId, printerId, activeSideId }: { filamentId: string; printerId?: string; activeSideId?: string }) {
  const query = useQuery({ queryKey: ['plate-compatibility', filamentId, printerId, activeSideId], queryFn: () => apiFetch<Ratings[]>(`/build-plate-ratings/filament/${filamentId}${printerId ? `?printer_id=${printerId}` : ''}`), staleTime: 10000 })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  if (query.isPending) return null
  if (query.error) return <small className="muted">Build plate compatibility unavailable</small>
  return <div className="plate-compatibility">{query.data?.map((scope) => {
    const active = scope.active_side_id ? scope.ratings[scope.active_side_id] : undefined
    const ranked = Object.entries(scope.ratings).filter(([, stars]) => stars > 0).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    const suggestions = ranked.map(([id, stars]) => {
      const plate = plates.data?.find((item) => item.surfaces.some((side) => side.id === id))
      const side = plate?.surfaces.find((item) => item.id === id)
      return side ? `${side.surface_code}: ${ratingLabel(stars)}` : null
    }).filter(Boolean).slice(0, 3)
    return <div key={`${scope.template_id}-${scope.printer_name}`} className={active === 0 ? 'warning-note' : 'muted'}><small>{scope.printer_name} · Active plate: {ratingLabel(active)}</small>{suggestions.length > 0 && <small className="table-subtext">Best plates: {suggestions.join(' · ')}</small>}</div>
  })}</div>
}
