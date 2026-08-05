import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Layers3, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, Printer } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime } from '../lib/format'

export default function BuildPlatesPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const [printerId, setPrinterId] = useState('')
  const selectPlate = useMutation({ mutationFn: (plateId: string) => apiFetch(`/build-plates/${plateId}/select`, { method: 'POST', body: JSON.stringify({ printer_id: printerId || printers.data?.[0]?.id }) }), onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ['plates'] }), client.invalidateQueries({ queryKey: ['printers'] }), client.invalidateQueries({ queryKey: ['dashboard'] })]) } })
  const activePlateIds = new Set(printers.data?.map((printer) => printer.active_plate_id).filter(Boolean))
  return <div><PageHeader eyebrow="P1–P5 surface library" title="Build plates" description="Keep slicer selection, saved Klipper mesh names, and physical plates aligned." actions={user?.role !== 'viewer' && printers.data?.length ? <label className="inline-field">Printer<select value={printerId || printers.data[0].id} onChange={(event) => setPrinterId(event.target.value)}>{printers.data.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label> : undefined} />{plates.isLoading ? <LoadingState /> : !plates.data?.length ? <EmptyState icon={Layers3} title="No plates configured" description="The workbook import establishes the required P1 through P5 plate records." /> : <section className="plate-grid">{plates.data.map((plate) => { const active = activePlateIds.has(plate.id); return <article className={`plate-tile${active ? ' plate-tile--active' : ''}`} key={plate.id}><div className="plate-illustration plate-illustration--large"><span>{plate.plate_code}</span>{active && <i><Check size={16} /></i>}</div><header><div><p className="eyebrow">{plate.plate_code}</p><h2>{plate.display_name}</h2></div><StatusPill status={active ? 'active' : plate.status} /></header><dl className="definition-list"><div><dt>Mesh profile</dt><dd>{plate.klipper_mesh_profile}</dd></div><div><dt>Surface</dt><dd>{plate.surface_type ?? 'Not specified'}</dd></div><div><dt>Condition</dt><dd>{plate.condition}</dd></div><div><dt>Last cleaned</dt><dd>{dateTime(plate.last_cleaned_at)}</dd></div></dl>{user?.role !== 'viewer' && <button className="button button--full" disabled={active || selectPlate.isPending || !printers.data?.length} onClick={() => selectPlate.mutate(plate.id)}><Sparkles size={17} />{active ? 'Active plate' : 'Select plate'}</button>}</article> })}</section>}</div>
}
