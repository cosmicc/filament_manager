import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import type { MaterialProfile } from '../api/types'
import { compactNumber } from '../lib/format'

/** Read-only template guidance; retain distinct settings scopes instead of guessing. */
export function DryingTemperatureDetails({ filamentId }: { filamentId: string }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const scoped = (profiles.data ?? []).filter((profile) => profile.filament_product_id === filamentId)
  return <div><dt>Filament drying temperature</dt><dd>
    {profiles.isError ? 'Unable to load' : profiles.isPending ? 'Loading…' : scoped.length === 0 ? 'Not set' : scoped.map((profile) => <div key={profile.id}>
      {profile.drying_temp_c == null ? 'Not set' : `${compactNumber(profile.drying_temp_c, 0)} °C`}
      {scoped.length > 1 ? ` · ${profile.base_template_name ?? 'Template'} · ${compactNumber(profile.nozzle_diameter_mm, 1)} mm nozzle` : ''}
    </div>)}
    <small>Set in the linked template only.</small>
  </dd></div>
}
