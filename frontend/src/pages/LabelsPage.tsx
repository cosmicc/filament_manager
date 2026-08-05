import { useQuery } from '@tanstack/react-query'
import { Download, Printer, QrCode, Search } from 'lucide-react'
import { type CSSProperties, useState } from 'react'
import { apiFetch } from '../api/client'
import type { Page, Spool } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'

export default function LabelsPage() {
  const [search, setSearch] = useState('')
  const query = useQuery({ queryKey: ['spools', 'labels', search], queryFn: () => apiFetch<Page<Spool>>(`/spools?limit=200${search ? `&search=${encodeURIComponent(search)}` : ''}`) })
  return <div><PageHeader eyebrow="Physical identification" title="Spool labels" description="Generate QR labels that contain only a stable Filament Manager spool URL." /><section className="toolbar"><label className="search-field"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a spool to label" /></label></section>{query.isLoading ? <LoadingState /> : !query.data?.items.length ? <EmptyState icon={QrCode} title="No spools to label" description="Add or import spool inventory first." /> : <section className="label-grid">{query.data.items.map((spool) => <article className="label-card" key={spool.id}><div className="label-card__preview"><img src={`/api/v1/spools/${spool.id}/label`} alt={`QR code for spool ${spool.spool_code}`} /><span className="filament-swatch" style={{ '--swatch': `#${spool.color_hex ?? '2F80A5'}` } as CSSProperties} /></div><div><p className="eyebrow">Filament Manager</p><h2>{spool.spool_code}</h2><p>{spool.vendor_name} {spool.material_type} · {spool.color_name}</p></div><div className="label-card__actions"><a className="button" href={`/api/v1/spools/${spool.id}/label`} download={`spool-${spool.spool_code}.png`}><Download size={16} /> Save</a><button className="button" onClick={() => window.open(`/api/v1/spools/${spool.id}/label`, '_blank')}><Printer size={16} /> Print</button></div></article>)}</section>}</div>
}
