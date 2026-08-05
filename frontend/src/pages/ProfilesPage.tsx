import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, MonitorUp, SlidersHorizontal, Upload } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { Filament, MaterialProfile, Printer } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'

export default function ProfilesPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const filaments = useQuery({ queryKey: ['filaments'], queryFn: () => apiFetch<Filament[]>('/filaments') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const publish = useMutation({ mutationFn: (id: string) => apiFetch(`/profiles/${id}/publish`, { method: 'POST' }), onSuccess: () => client.invalidateQueries({ queryKey: ['profiles'] }) })
  const [deploymentMessage, setDeploymentMessage] = useState<string | null>(null)
  const deploy = useMutation({
    mutationFn: (id: string) => apiFetch(`/profiles/${id}/deployments`, { method: 'POST', body: '{}' }),
    onSuccess: () => setDeploymentMessage('Deployment queued for every active Cura workstation.'),
    onError: (error: Error) => setDeploymentMessage(error.message),
  })
  const filamentName = (id: string) => { const item = filaments.data?.find((value) => value.id === id); return item ? `${item.vendor_name ?? ''} ${item.material_type} · ${item.color_name}`.trim() : 'Unknown filament' }
  const printerName = (id: string) => printers.data?.find((value) => value.id === id)?.name ?? 'Unknown printer'
  return <div><PageHeader eyebrow="Slicer-ready settings" title="Material profiles" description="Versioned, auditable settings derived from the calibration workflow." />{deploymentMessage && <div className="deployment-note" role="status">{deploymentMessage}</div>}{profiles.isLoading ? <LoadingState /> : !profiles.data?.length ? <EmptyState icon={SlidersHorizontal} title="No profiles yet" description="Complete a six-step calibration session to publish the first material profile." /> : <div className="table-card"><table><thead><tr><th>Filament</th><th>Printer</th><th>Version</th><th>Temperatures</th><th>Flow</th><th>Pressure advance</th><th>Status</th><th>Actions</th></tr></thead><tbody>{profiles.data.map((profile) => <tr key={profile.id}><td><strong>{filamentName(profile.filament_product_id)}</strong></td><td>{printerName(profile.printer_id)} · {profile.nozzle_diameter_mm} mm</td><td>v{profile.version}</td><td>{profile.extruder_temp_c}° / {profile.bed_temp_c}°</td><td>{profile.flow_percent}%</td><td>{profile.pressure_advance ?? '—'}</td><td><StatusPill status={profile.status} /></td><td><div className="table-actions">{user?.role !== 'viewer' && profile.status !== 'published' && <button className="icon-button" onClick={() => publish.mutate(profile.id)} title="Publish profile"><Upload size={17} /></button>}{user?.role !== 'viewer' && profile.status === 'published' && <button className="icon-button" disabled={deploy.isPending} onClick={() => deploy.mutate(profile.id)} title="Deploy to all Cura workstations"><MonitorUp size={17} /></button>}<a className="icon-button" href={`/api/v1/profiles/${profile.id}/exports/cura`} title="Download Cura profile"><Download size={17} /></a></div></td></tr>)}</tbody></table></div>}</div>
}
