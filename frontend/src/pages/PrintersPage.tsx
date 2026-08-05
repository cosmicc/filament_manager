import { useQuery } from '@tanstack/react-query'
import { Clock3, Printer as PrinterIcon, Wifi } from 'lucide-react'
import { apiFetch } from '../api/client'
import type { BuildPlate, Printer } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { dateTime } from '../lib/format'

export default function PrintersPage() {
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  return <div><PageHeader eyebrow="Moonraker context" title="Printers" description="Canonical printer state without exposing internal service addresses to the browser." />{printers.isLoading ? <LoadingState /> : !printers.data?.length ? <EmptyState icon={PrinterIcon} title="No printers configured" description="Add a printer and its Moonraker connection in the server-side YAML configuration." /> : <section className="printer-grid">{printers.data.map((printer) => { const plate = plates.data?.find((item) => item.id === printer.active_plate_id); return <article className="printer-card card" key={printer.id}><div className="printer-card__hero"><span><PrinterIcon size={28} /></span><StatusPill status={printer.status} /></div><h2>{printer.name}</h2><p className="muted">{printer.printer_code} · {printer.nozzle_diameter_mm} mm nozzle</p><dl className="definition-list"><div><dt>Active plate</dt><dd>{plate ? `${plate.plate_code} · ${plate.display_name}` : 'Not selected'}</dd></div><div><dt><Clock3 size={14} /> Last seen</dt><dd>{dateTime(printer.last_seen_at)}</dd></div></dl><p className="security-note"><Wifi size={16} /> Connection details remain server-side.</p></article> })}</section>}</div>
}
