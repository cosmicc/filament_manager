import { useQuery } from '@tanstack/react-query'
import { PackageOpen, Search } from 'lucide-react'
import { type CSSProperties, useState } from 'react'
import { apiFetch } from '../api/client'
import type { Filament } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { grams } from '../lib/format'

export default function FilamentsPage() {
  const [search, setSearch] = useState('')
  const query = useQuery({ queryKey: ['filaments', search], queryFn: () => apiFetch<Filament[]>(`/filaments${search ? `?search=${encodeURIComponent(search)}` : ''}`) })
  return <div><PageHeader eyebrow="Product catalog" title="Filaments" description="Controlled material definitions shared by physical spools and calibration profiles." /><section className="toolbar"><label className="search-field"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search material, product, or color" aria-label="Search filaments" /></label><span className="toolbar__summary">{query.data?.length ?? 0} products</span></section>{query.isLoading ? <LoadingState /> : !query.data?.length ? <EmptyState icon={PackageOpen} title="No filament products" description="Import the workbook or create a product through the API to populate this catalog." /> : <section className="catalog-grid">{query.data.map((filament) => <article className="catalog-card" key={filament.id}><span className="filament-swatch filament-swatch--hero" style={{ '--swatch': `#${filament.color_hex ?? '2F80A5'}` } as CSSProperties} /><div><p className="eyebrow">{filament.vendor_name ?? 'Unspecified vendor'}</p><h2>{filament.product_name ?? `${filament.material_type} ${filament.color_name}`}</h2><p>{filament.material_type}{filament.filler ? ` · ${filament.filler}` : ''}{filament.finish ? ` · ${filament.finish}` : ''}</p></div><dl className="catalog-meta"><div><dt>Color</dt><dd>{filament.color_name}</dd></div><div><dt>Diameter</dt><dd>{filament.diameter_mm} mm</dd></div><div><dt>Density</dt><dd>{filament.density_g_cm3} g/cm³</dd></div><div><dt>Nominal</dt><dd>{grams(filament.nominal_net_mass_g)}</dd></div></dl></article>)}</section>}</div>
}
