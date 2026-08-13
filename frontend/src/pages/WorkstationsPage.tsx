import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Clipboard, FileInput, Library, MonitorCog, Power, PowerOff, RefreshCw, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, CuraDeployment, CuraMaterialReport, MaterialTemplate, Printer, WorkstationAgent, WorkstationPairingCode } from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { Link } from '../context/RouterContext'
import { dateTime } from '../lib/format'

function platformLabel(platform: WorkstationAgent['platform']) {
  return platform === 'windows_11' ? 'Windows 11' : 'Arch Linux'
}

interface CuraTemplateImportSelection {
  agent: WorkstationAgent
  material: CuraMaterialReport
}

export default function WorkstationsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [pairing, setPairing] = useState<WorkstationPairingCode | null>(null)
  const [copied, setCopied] = useState(false)
  const [importSelection, setImportSelection] = useState<CuraTemplateImportSelection | null>(null)
  const [importPrinterId, setImportPrinterId] = useState('')
  const [importNozzleDiameter, setImportNozzleDiameter] = useState('0.4')
  const [message, setMessage] = useState('')
  const agents = useQuery({ queryKey: ['workstation-agents'], queryFn: () => apiFetch<WorkstationAgent[]>('/workstation-agents'), refetchInterval: 15_000 })
  const deployments = useQuery({ queryKey: ['cura-deployments'], queryFn: () => apiFetch<CuraDeployment[]>('/cura-deployments'), refetchInterval: 10_000 })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=true'), refetchInterval: 15_000 })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const createPairing = useMutation({
    mutationFn: () => apiFetch<WorkstationPairingCode>('/workstation-agents/pairing-codes', { method: 'POST' }),
    onSuccess: (value) => { setPairing(value); setCopied(false) },
  })
  const toggleAgent = useMutation({
    mutationFn: (agent: WorkstationAgent) => apiFetch(`/workstation-agents/${agent.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ expected_version: agent.record_version, enabled: !agent.enabled }),
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workstation-agents'] }),
  })
  const synchronizeCura = useMutation({
    mutationFn: (agent: WorkstationAgent) => apiFetch(`/workstation-agents/${agent.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ expected_version: agent.record_version, cura_management_enabled: true }),
    }),
    onSuccess: async () => {
      setMessage('Authoritative Cura synchronization was queued.')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workstation-agents'] }),
        queryClient.invalidateQueries({ queryKey: ['cura-deployments'] }),
      ])
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const importTemplate = useMutation({
    mutationFn: (payload: Record<string, string | null>) => apiFetch<MaterialTemplate>('/profiles/templates/import-cura-material', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
    onSuccess: async () => {
      setMessage('Cura material preserved as a draft template. Review and publish it before managing this workstation.')
      setImportSelection(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['material-templates'] }),
        queryClient.invalidateQueries({ queryKey: ['workstation-agents'] }),
      ])
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const openTemplateImport = (agent: WorkstationAgent, material: CuraMaterialReport) => {
    const printer = printers.data?.[0]
    setImportPrinterId(printer?.id ?? '')
    setImportNozzleDiameter(printer?.nozzle_diameter_mm ?? '0.4')
    setImportSelection({ agent, material })
    setMessage('')
  }
  const copyPairing = async () => {
    if (!pairing) return
    await navigator.clipboard.writeText(pairing.pairing_code)
    setCopied(true)
  }
  return <div>
    <PageHeader eyebrow="Cura automation" title="Cura workstations" description="Synchronize the complete managed library and import edits to known templates or profiles as reviewable drafts. New materials remain app-only." actions={user?.role === 'administrator' ? <button className="button button--primary" onClick={() => createPairing.mutate()} disabled={createPairing.isPending}><ShieldCheck size={17} /> Create pairing code</button> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    {pairing && <section className="pairing-card card" aria-live="polite">
      <div><h2>Pairing code</h2><p>Valid until {dateTime(pairing.expires_at)}. It can enroll one workstation and is never shown again.</p></div>
      <div className="pairing-code"><code>{pairing.pairing_code}</code><button className="icon-button" onClick={() => void copyPairing()} aria-label="Copy pairing code">{copied ? <Check size={18} /> : <Clipboard size={18} />}</button></div>
      <p className="muted">On that workstation, install the agent and run <code>filament-manager-agent pair --server https://your-filament-manager.example --name &quot;Cura workstation&quot;</code>. Paste the code only at the hidden prompt.</p>
    </section>}
    {createPairing.error && <div className="form-error">{createPairing.error.message}</div>}
    <div className="section-heading"><h2>Paired workstations</h2><button className="icon-button" onClick={() => void agents.refetch()} aria-label="Refresh workstations"><RefreshCw size={17} /></button></div>
    {agents.isLoading || templates.isLoading || printers.isLoading || plates.isLoading ? <LoadingState /> : !agents.data?.length ? <EmptyState icon={MonitorCog} title="No workstations paired" description="Create a one-time code, install the agent under your normal workstation account, and pair it with Filament Manager." /> : <div className="workstation-grid">{agents.data.map((agent) => {
      const importedTemplates = (templates.data ?? []).filter((template) => template.source_workstation_agent_id === agent.id)
      const pendingImportedTemplates = importedTemplates.filter((template) => !template.active || !template.revisions.some((revision) => revision.status === 'published'))
      return <article className="workstation-card card" key={agent.id}>
      <header><span className={`health-dot ${agent.enabled && agent.last_seen_at ? 'health-dot--connected' : 'health-dot--disabled'}`} /><div><h2>{agent.display_name}</h2><p>{platformLabel(agent.platform)} · {agent.hostname} · Agent {agent.agent_version}</p></div><StatusPill status={agent.enabled ? 'active' : 'disabled'} /></header>
      <dl className="definition-list"><div><dt>Last contact</dt><dd>{agent.last_seen_at ? dateTime(agent.last_seen_at) : 'Never'}</dd></div><div><dt>Cura installations</dt><dd>{agent.cura_installations.length}</dd></div><div><dt>Material library</dt><dd>{agent.cura_management_enabled ? 'Authoritative with draft edit intake' : 'Not managed'}</dd></div><div><dt>Existing user materials</dt><dd>{String(agent.capabilities.unmanaged_material_count ?? 'Unknown')}</dd></div><div><dt>Agent ID</dt><dd>{agent.agent_code}</dd></div></dl>
      {agent.cura_installations.map((installation) => <div className="cura-installation" key={installation.installation_id}><strong>Cura {installation.version}</strong><small>{installation.channel} · Settings v{installation.setting_version ?? 'unknown'}</small>{installation.machines.length ? <span>{installation.machines.map((machine) => `${machine.display_name}${machine.nozzle_diameter_mm ? ` · ${machine.nozzle_diameter_mm} mm` : ''}`).join(', ')}</span> : <span>No machine instances detected</span>}</div>)}
      {!agent.cura_management_enabled && agent.cura_materials.length ? <section className="cura-preservation" aria-label={`Cura materials reported by ${agent.display_name}`}>
        <div><h3>Preserve before takeover</h3><p className="muted">Import any material you want to keep as a draft template. Imported drafts must be reviewed and published before authoritative synchronization.</p></div>
        <div className="cura-material-list">{agent.cura_materials.map((material) => {
          const imported = importedTemplates.find((template) => template.source_cura_material_id === material.source_id)
          const preserved = Boolean(imported?.active && imported.revisions.some((revision) => revision.status === 'published'))
          return <article className="cura-material-item" key={`${material.installation_id}:${material.source_id}`}>
            <div><strong>{material.name}</strong><small>{material.material_type} · {Object.keys(material.settings).length} approved settings</small></div>
            {preserved ? <div className="cura-material-item__status"><StatusPill status="published" /><Link className="button button--small" to="/templates">View template</Link></div> : imported ? <div className="cura-material-item__status"><StatusPill status="draft" /><Link className="button button--small" to="/templates">Review and publish</Link></div> : user?.role === 'administrator' && printers.data?.length ? <button className="button button--small" type="button" onClick={() => openTemplateImport(agent, material)}><FileInput size={15} /> Import as draft</button> : <span className="muted">{user?.role === 'administrator' ? 'Add a printer before importing' : 'Not imported'}</span>}
          </article>
        })}</div>
        {pendingImportedTemplates.length ? <p className="form-error" role="status">Publish {pendingImportedTemplates.length} imported template{pendingImportedTemplates.length === 1 ? '' : 's'} before managing and synchronizing this workstation.</p> : null}
      </section> : null}
      {agent.last_error && <p className="form-error">{agent.last_error}</p>}
      {user?.role === 'administrator' && <div className="template-card__actions"><button className="button" disabled={synchronizeCura.isPending || pendingImportedTemplates.length > 0} onClick={() => {
        if (pendingImportedTemplates.length) {
          setMessage('Review and publish every imported Cura template before managing this workstation.')
          return
        }
        if (!agent.cura_management_enabled && !window.confirm('Filament Manager will back up and replace every user material file in each detected Cura version, then hide Cura bundled materials in the selectors. Continue?')) return
        synchronizeCura.mutate(agent)
      }}><Library size={16} />{agent.cura_management_enabled ? 'Synchronize library' : 'Manage and synchronize Cura'}</button><button className="button" disabled={toggleAgent.isPending} onClick={() => toggleAgent.mutate(agent)}>{agent.enabled ? <PowerOff size={16} /> : <Power size={16} />}{agent.enabled ? 'Revoke agent' : 'Enable agent'}</button></div>}
    </article>})}</div>}
    <div className="section-heading"><h2>Recent deployments</h2></div>
    {deployments.isLoading ? <LoadingState /> : !deployments.data?.length ? <EmptyState icon={RefreshCw} title="No Cura synchronizations yet" description="Publish a template or product profile, then enable authoritative management on a workstation." /> : <div className="table-card"><table><thead><tr><th>Workstation</th><th>Status</th><th>Attempts</th><th>Requested</th><th>Completed</th><th>Detail</th></tr></thead><tbody>{deployments.data.map((deployment) => <tr key={deployment.id}><td>{agents.data?.find((item) => item.id === deployment.agent_id)?.display_name ?? deployment.agent_id.slice(0, 8)}</td><td><StatusPill status={deployment.status} /></td><td>{deployment.attempts}</td><td>{dateTime(deployment.created_at)}</td><td>{deployment.completed_at ? dateTime(deployment.completed_at) : '—'}</td><td>{deployment.last_error_message ?? (deployment.status === 'succeeded' ? 'Full library installed with automatic backup' : 'Waiting for agent or Cura to close')}</td></tr>)}</tbody></table></div>}
    {importSelection ? <Modal title="Import Cura material as template" description="Create a reviewable draft without changing the workstation. Publish it before enabling authoritative Cura management." onClose={() => setImportSelection(null)} size="wide" footer={<><button className="button" type="button" onClick={() => setImportSelection(null)}>Cancel</button><button className="button button--primary" type="submit" form="import-cura-template" disabled={importTemplate.isPending}><FileInput size={16} />{importTemplate.isPending ? 'Importing…' : 'Import draft template'}</button></>}>
      <form id="import-cura-template" className="editor-form" onSubmit={(event) => {
        event.preventDefault()
        const data = new FormData(event.currentTarget)
        importTemplate.mutate({
          agent_id: importSelection.agent.id,
          source_id: importSelection.material.source_id,
          name: `Template ${String(data.get('material_type') ?? '').trim()}`,
          material_type: String(data.get('material_type') ?? '').trim(),
          description: String(data.get('description') ?? '').trim() || null,
          printer_id: importPrinterId,
          nozzle_diameter_mm: importNozzleDiameter,
          filament_diameter_mm: String(data.get('filament_diameter_mm') ?? ''),
          filament_density_g_cm3: String(data.get('filament_density_g_cm3') ?? ''),
          preferred_build_plate_surface_id: String(data.get('preferred_build_plate_surface_id') ?? '') || null,
        })
      }}>
        <EditorSection title="Cura source" description="Only the approved material-scoped settings already reported by the workstation are copied.">
          <dl className="definition-list"><div><dt>Material</dt><dd>{importSelection.material.name}</dd></div><div><dt>Workstation</dt><dd>{importSelection.agent.display_name}</dd></div><div><dt>Approved settings</dt><dd>{Object.keys(importSelection.material.settings).length}</dd></div></dl>
        </EditorSection>
        <EditorSection title="Draft template identity" description="Choose the generic material family and the exact printer/nozzle scope to preserve.">
          <div className="form-grid">
            <label>Material type<input name="material_type" defaultValue={importSelection.material.material_type} required autoFocus /><small className="field-help">Saved as Template {importSelection.material.material_type} under the Template brand in Cura.</small></label>
            <label>Printer<select name="printer_id" value={importPrinterId} required onChange={(event) => {
              const selected = printers.data?.find((printer) => printer.id === event.target.value)
              setImportPrinterId(event.target.value)
              setImportNozzleDiameter(selected?.nozzle_diameter_mm ?? '0.4')
            }}>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label>
            <label>Nozzle diameter<input name="nozzle_diameter_mm" type="number" min="0.1" step="0.05" value={importNozzleDiameter} onChange={(event) => setImportNozzleDiameter(event.target.value)} required /></label>
            <label>Filament diameter<input name="filament_diameter_mm" type="number" min="0.1" step="0.01" defaultValue="1.75" required /></label>
            <label>Filament density<input name="filament_density_g_cm3" type="number" min="0.01" step="0.001" placeholder="1.24" required /></label>
            <label className="form-grid__wide">Preferred plate side<select name="preferred_build_plate_surface_id"><option value="">No preference</option>{plates.data?.flatMap((plate) => plate.surfaces.map((surface) => <option key={surface.id} value={surface.id}>{surface.surface_code} · {surface.surface_material ?? 'Surface not specified'}</option>))}</select></label>
            <label className="form-grid__wide">Description<textarea name="description" rows={2} placeholder="Import source and review notes" /></label>
          </div>
        </EditorSection>
        {importTemplate.error ? <p className="form-error" role="alert">{importTemplate.error.message}</p> : null}
      </form>
    </Modal> : null}
  </div>
}
