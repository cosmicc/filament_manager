import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import type { MaterialProfile } from '../api/types'
import { compactNumber } from '../lib/format'

/** Read-only template guidance; retain distinct settings scopes instead of guessing. */
export function DryingTemperatureDetails({ filamentId }: { filamentId: string }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const scoped = (profiles.data ?? []).filter((profile) => profile.filament_product_id === filamentId)
  const fields = [
    ['drying_temp_c', 'Filament drying temperature'],
    ['drying_time_hours', 'Filament drying time'],
    ['moisture_sensitivity', 'Filament moisture sensitivity'],
  ] as const
  return <>{fields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>
    {profiles.isError ? 'Unable to load' : profiles.isPending ? 'Loading…' : scoped.length === 0 ? 'Not set' : scoped.map((profile) => <div key={profile.id}>
      {profile[key] == null ? 'Not set' : key === 'drying_temp_c' ? `${compactNumber(profile[key], 0)} °C` : key === 'drying_time_hours' ? `${profile[key]} hours` : String(profile[key]).replace(/^./, (letter) => letter.toUpperCase())}
      {scoped.length > 1 ? ` · ${profile.base_template_name ?? 'Template'} · ${compactNumber(profile.nozzle_diameter_mm, 1)} mm nozzle` : ''}
    </div>)}
    <small>Set in the linked template only.</small>
  </dd></div>)}</>
}
