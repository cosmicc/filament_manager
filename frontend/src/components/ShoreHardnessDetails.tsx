import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import type { MaterialProfile } from '../api/types'
import { compactNumber } from '../lib/format'
import { formatHardness } from '../lib/shoreHardness'
import { ShoreHardnessReference } from './ShoreHardnessReference'

/** Show effective hardness for each exact current scope without picking a printer. */
export function ShoreHardnessDetails({ filamentId }: { filamentId: string }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const scoped = (profiles.data ?? []).filter((profile) => profile.filament_product_id === filamentId)
  return <div><dt>Shore hardness</dt><dd>{profiles.isError ? 'Unable to load' : profiles.isPending ? 'Loading…' : !scoped.length ? 'Not set' : scoped.map((profile) => <div key={profile.id}>{formatHardness(profile.shore_hardness)}{scoped.length > 1 ? ` · ${profile.base_template_name ?? 'Template'} · ${compactNumber(profile.nozzle_diameter_mm, 1)} mm nozzle` : ''}</div>)}<ShoreHardnessReference /></dd></div>
}
