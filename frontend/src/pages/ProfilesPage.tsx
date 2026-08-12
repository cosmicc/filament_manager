import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileInput, MonitorUp, SlidersHorizontal, Upload } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type {
  BuildPlate,
  Filament,
  MaterialProfile,
  Printer,
  WorkstationAgent,
} from '../api/types'
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
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const agents = useQuery({ queryKey: ['workstation-agents'], queryFn: () => apiFetch<WorkstationAgent[]>('/workstation-agents') })
  const publish = useMutation({ mutationFn: (id: string) => apiFetch(`/profiles/${id}/publish`, { method: 'POST' }), onSuccess: () => client.invalidateQueries({ queryKey: ['profiles'] }) })
  const [deploymentMessage, setDeploymentMessage] = useState<string | null>(null)
  const deploy = useMutation({
    mutationFn: (id: string) => apiFetch(`/profiles/${id}/deployments`, { method: 'POST', body: '{}' }),
    onSuccess: () => setDeploymentMessage('Complete authoritative Cura library queued for every managed workstation.'),
    onError: (error: Error) => setDeploymentMessage(error.message),
  })
  const importMaterial = useMutation({
    mutationFn: (payload: Record<string, string | null>) => apiFetch('/profiles/import-cura-material', { method: 'POST', body: JSON.stringify(payload) }),
    onSuccess: async () => {
      setDeploymentMessage('Cura material imported as a new draft profile.')
      await client.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (error: Error) => setDeploymentMessage(error.message),
  })
  const materialOptions = (agents.data ?? []).flatMap((agent) =>
    agent.cura_materials.map((material) => ({
      key: `${agent.id}:${material.source_id}`,
      agentId: agent.id,
      sourceId: material.source_id,
      label: `${material.name} · ${agent.display_name}`,
      settingCount: Object.keys(material.settings).length,
    })),
  )
  const filamentName = (id: string) => {
    const item = filaments.data?.find((value) => value.id === id)
    return item ? `${item.vendor_name ?? ''} ${item.material_type} · ${item.color_name}`.trim() : 'Unknown filament'
  }
  const printerName = (id: string) => printers.data?.find((value) => value.id === id)?.name ?? 'Unknown printer'

  return (
    <div>
      <PageHeader eyebrow="Slicer-ready settings" title="Material profiles" description="Product-specific Cura settings copied from a generic template, then tuned and published independently." />
      {deploymentMessage ? <div className="deployment-note" role="status">{deploymentMessage}</div> : null}
      {user?.role !== 'viewer' && materialOptions.length ? (
        <section className="card profile-import-card">
          <header className="card__header"><div><p className="eyebrow">Existing Cura library</p><h2>Import a material</h2></div><FileInput size={21} /></header>
          <p className="muted">Copy the approved Material Settings values into a new Filament Manager draft. The local Cura file is never modified during import.</p>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault()
              const data = new FormData(event.currentTarget)
              const materialKey = String(data.get('material') ?? '')
              const option = materialOptions.find((item) => item.key === materialKey)
              const printerId = String(data.get('printer_id') ?? '')
              const printer = printers.data?.find((item) => item.id === printerId)
              if (!option || !printer) return
              importMaterial.mutate({
                agent_id: option.agentId,
                source_id: option.sourceId,
                filament_product_id: String(data.get('filament_product_id') ?? ''),
                printer_id: printerId,
                nozzle_diameter_mm: printer.nozzle_diameter_mm,
                preferred_build_plate_surface_id: String(data.get('preferred_build_plate_surface_id') ?? '') || null,
              })
            }}
          >
            <label>Cura material<select name="material" required>{materialOptions.map((option) => <option key={option.key} value={option.key}>{option.label} ({option.settingCount} settings)</option>)}</select></label>
            <label>Canonical filament<select name="filament_product_id" required>{filaments.data?.map((filament) => <option key={filament.id} value={filament.id}>{filamentName(filament.id)}</option>)}</select></label>
            <label>Printer and nozzle<select name="printer_id" required>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name} · {printer.nozzle_diameter_mm} mm</option>)}</select></label>
            <label>Preferred plate side<select name="preferred_build_plate_surface_id"><option value="">No preference</option>{plates.data?.flatMap((plate) => plate.surfaces.map((surface) => <option key={surface.id} value={surface.id}>{surface.surface_code} · {surface.surface_material ?? 'Surface not specified'}</option>))}</select></label>
            <div className="form-actions"><button className="button button--primary" disabled={importMaterial.isPending} type="submit"><FileInput size={17} />{importMaterial.isPending ? 'Importing…' : 'Import as draft'}</button></div>
          </form>
        </section>
      ) : null}
      {profiles.isLoading ? <LoadingState /> : !profiles.data?.length ? (
        <EmptyState icon={SlidersHorizontal} title="No profiles yet" description={materialOptions.length ? 'Import an existing Cura material above or complete a calibration session.' : 'Complete a calibration session, or let a paired workstation report existing Cura materials for import.'} />
      ) : (
        <div className="table-card"><table><thead><tr><th>Filament</th><th>Printer</th><th>Version</th><th>Temperatures</th><th>Flow</th><th>Cura settings</th><th>Pressure advance</th><th>Status</th><th>Actions</th></tr></thead><tbody>{profiles.data.map((profile) => <tr key={profile.id}><td><strong>{filamentName(profile.filament_product_id)}</strong></td><td>{printerName(profile.printer_id)} · {profile.nozzle_diameter_mm} mm</td><td>v{profile.version}</td><td>{profile.extruder_temp_c}° / {profile.bed_temp_c}°</td><td>{profile.flow_percent}%</td><td>{Object.keys(profile.cura_settings).length} stored</td><td>{profile.pressure_advance ?? '—'}</td><td><StatusPill status={profile.status} /></td><td><div className="table-actions">{user?.role !== 'viewer' && profile.status !== 'published' && <button className="icon-button" onClick={() => publish.mutate(profile.id)} title="Publish profile"><Upload size={17} /></button>}{user?.role !== 'viewer' && profile.status === 'published' && <button className="icon-button" disabled={deploy.isPending} onClick={() => deploy.mutate(profile.id)} title="Deploy material to all Cura workstations"><MonitorUp size={17} /></button>}<a className="icon-button" href={`/api/v1/profiles/${profile.id}/exports/cura`} title="Download Cura material settings"><Download size={17} /></a></div></td></tr>)}</tbody></table></div>
      )}
    </div>
  )
}
