import { useQuery } from '@tanstack/react-query'
import { MapPin } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { Page, Spool } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useRouter } from '../context/RouterContext'
import { filamentSwatchStyle } from '../lib/colors'
import { grams } from '../lib/format'
import { materialIdentitySummary } from '../lib/materialIdentity'

interface SpoolLocation {
  location: string | null
  spool_count: number
  remaining_mass_g: string
}

/** Browse canonical free-text groups and reuse the normal spool-detail workflow. */
export default function LocationsPage() {
  const { navigate } = useRouter()
  const [selected, setSelected] = useState<string | null | undefined>(undefined)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [page, setPage] = useState<{ location: string | null | undefined; offset: number }>({ location: undefined, offset: 0 })
  const locations = useQuery({
    queryKey: ['locations', includeArchived],
    queryFn: () => apiFetch<SpoolLocation[]>(`/locations?include_archived=${includeArchived}`),
    refetchInterval: 15_000,
  })
  const groups = locations.data ?? []
  const active = groups.find((item) => item.location === selected) ?? groups[0]
  // If polling removes the selected group, start the replacement on page one.
  const offset = page.location === active?.location ? page.offset : 0
  const setOffset = (value: number) => setPage({ location: active?.location, offset: value })
  const parameters = new URLSearchParams({ limit: '50', offset: String(offset), include_archived: String(includeArchived) })
  if (active?.location == null) parameters.set('unassigned', 'true')
  else parameters.set('location_exact', active.location)
  const spools = useQuery({
    queryKey: ['spools', 'location', active?.location, includeArchived, offset],
    queryFn: () => apiFetch<Page<Spool>>(`/spools?${parameters}`),
    enabled: Boolean(active),
    refetchInterval: 15_000,
  })
  const spoolCount = spools.data?.total ?? active?.spool_count ?? 0

  return <div>
    <PageHeader eyebrow="Physical inventory" title="Locations" description="Browse spool storage locations. Open any spool for its usual details and actions." />
    <section className="toolbar">
      <label className="check-row"><input type="checkbox" checked={includeArchived} onChange={(event) => { setIncludeArchived(event.target.checked); setOffset(0) }} />Include archived spools</label>
      <span className="toolbar__summary">{groups.length} location groups</span>
    </section>
    {locations.isError ? <p className="form-error" role="alert">Locations could not be loaded.</p> : locations.isPending ? <LoadingState label="Loading locations" /> : !groups.length ? <EmptyState icon={MapPin} title="No spool locations yet" description="Add a spool and enter its Location to see it here." /> : <>
      <section className="collection-grid collection-grid--cards" aria-label="Spool locations">
        {groups.map((item) => <button key={JSON.stringify(item.location)} className="collection-card collection-card--button location-card" aria-pressed={active?.location === item.location} onClick={() => { setSelected(item.location); setOffset(0) }}>
          <header className="collection-card__header"><MapPin size={20} /><h2>{item.location ?? 'Unassigned'}</h2></header>
          <dl className="catalog-meta"><div><dt>Spools</dt><dd>{item.spool_count}</dd></div><div><dt>Filament remaining</dt><dd>{grams(item.remaining_mass_g, 1)}</dd></div></dl>
        </button>)}
      </section>
      <section className="location-spools" aria-label="Spools in selected location">
        <div className="toolbar">
          <h2>{active?.location ?? 'Unassigned'}</h2>
          <span className="toolbar__summary">{spoolCount} {spoolCount === 1 ? 'spool' : 'spools'}</span>
          <button className="button" disabled={offset === 0 || spools.isFetching} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
          <button className="button" disabled={spools.isFetching || !spools.data || offset + 50 >= spools.data.total} onClick={() => setOffset(offset + 50)}>Next</button>
        </div>
        {spools.isError ? <p className="form-error" role="alert">Spools in this location could not be loaded.</p> : spools.isPending ? <LoadingState label="Loading location spools" /> : !spools.data?.items.length ? <p className="muted">No spools on this page. Choose Previous or another location.</p> : <div className="collection-grid collection-grid--cards">
          {spools.data.items.map((spool) => <button key={spool.id} className="collection-card collection-card--button" onClick={() => navigate(`/spools?spool_id=${encodeURIComponent(spool.id)}`)}>
            <header className="collection-card__header"><div className="table-identity"><span className="filament-swatch" style={filamentSwatchStyle(spool.color_mode, spool.color_hexes, spool.color_hex ?? '2F80A5')} /><span><strong>{spool.spool_code}</strong><small>{spool.vendor_name ?? 'Unspecified manufacturer'}</small></span></div><StatusPill status={spool.status} /></header>
            <div className="collection-card__body"><h2 title={materialIdentitySummary(spool)}>{materialIdentitySummary(spool)}</h2><p>{grams(spool.remaining_mass_effective_g, 1)} filament remaining</p></div>
            <span className="collection-card__link">Open spool details</span>
          </button>)}
        </div>}
      </section>
    </>}
  </div>
}
