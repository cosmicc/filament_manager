import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import { grams } from '../lib/format'

interface TareSuggestion {
  tare_mass_g: string
  nominal_net_mass_g: string
  spool_count: number
}

/** Saved manufacturer observations are advisory, never automatically selected. */
export function SpoolTareSuggestions({ filamentId, disabled = false, onApply }: {
  filamentId: string
  disabled?: boolean
  onApply: (tare: string) => void
}) {
  const query = useQuery({
    queryKey: ['spool-tare-suggestions', filamentId],
    queryFn: () => apiFetch<TareSuggestion[]>(`/spool-tare-suggestions?filament_product_id=${encodeURIComponent(filamentId)}`),
    enabled: Boolean(filamentId),
  })
  return <div className="form-grid__wide">
    <label>Previously saved empty-spool weights
      <select aria-label="Suggested empty-spool weight" value="" disabled={disabled || !query.data?.length} onChange={(event) => {
        if (event.target.value === '') return
        const suggestion = query.data?.[Number(event.target.value)]
        if (suggestion) onApply(suggestion.tare_mass_g)
      }}>
        <option value="">{query.isLoading ? 'Loading suggestions…' : query.data?.length ? 'Choose a weight to apply' : 'No saved weights for this manufacturer'}</option>
        {(query.data ?? []).map((item, index) => <option key={`${item.tare_mass_g}-${item.nominal_net_mass_g}`} value={index}>
          {grams(item.tare_mass_g, 1)} empty · {grams(item.nominal_net_mass_g, 1)} filament capacity · {item.spool_count} saved {item.spool_count === 1 ? 'spool' : 'spools'}
        </option>)}
      </select>
    </label>
    <p className="field-help">Same manufacturer, most common first. Spool designs vary; verify before applying.{disabled ? ' Tare inferred from this unused spool’s scale weight takes priority.' : ''}</p>
    {query.isError ? <p className="form-error" role="alert">Weight suggestions could not be loaded. You can still enter a known weight.</p> : null}
  </div>
}
