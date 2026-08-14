import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Clipboard, FileInput, Library, MonitorCog, Power, PowerOff, RefreshCw, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, CuraMaterialReport, Filament, MaterialProfile, MaterialTemplate, Printer, WorkstationAgent, WorkstationPairingCode } from '../api/types'
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
  const [importTarget, setImportTarget] = useState<'template' | 'profile'>('template')
  const [importFilamentId, setImportFilamentId] = useState('')
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState('')
  const agents = useQuery({ queryKey: ['workstation-agents'], queryFn: () => apiFetch<WorkstationAgent[]>('/workstation-agents'), refetchInterval: 15_000 })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=true'), refetchInterval: 15_000 })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const filaments = useQuery({ queryKey: ['filaments'], queryFn: () => apiFetch<Filament[]>('/filaments') })
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
        queryClient.invalidateQueries({ queryKey: ['diagnostics'] }),
      ])
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const importMaterial = useMutation({
    mutationFn: ({ target, payload }: { target: 'template' | 'profile'; payload: Record<string, string | null> }) => apiFetch<MaterialTemplate | MaterialProfile>(target === 'template' ? '/profiles/templates/import-cura-material' : '/profiles/import-cura-material', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
    onSuccess: async (_, variables) => {
      const sourceKey = importSelection ? `${importSelection.agent.id}:${importSelection.material.source_id}` : ''
      setMessage(variables.target === 'template' ? 'Cura material preserved as a draft template. Review and publish it before takeover.' : 'Cura material preserved as a filament-specific draft profile. Review and publish it before takeover.')
      setSelectedSources((current) => { const next = new Set(current); next.delete(sourceKey); return next })
      setImportSelection(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['material-templates'] }),
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
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
    const existingTemplate = templates.data?.some((template) => template.active && template.material_type.toLowerCase() === material.material_type.toLowerCase() && template.printer_id === printer?.id && template.nozzle_diameter_mm === (printer?.nozzle_diameter_mm ?? '0.4'))
    setImportTarget(existingTemplate ? 'profile' : 'template')
    setImportFilamentId(filaments.data?.find((filament) => filament.material_type.toLowerCase() === material.material_type.toLowerCase())?.id ?? filaments.data?.[0]?.id ?? '')
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
    <section className="card diagnostic-actions cura-takeover-guide"><div><p className="eyebrow">One-time takeover setup</p><h2>Preserve selected Cura materials before synchronization</h2><ol><li>Pair the workstation and wait for Cura discovery.</li><li>Select material files worth preserving and import one generic family source as the template.</li><li>Import other same-family sources as filament-specific profiles, then review and publish every draft.</li><li>Start authoritative synchronization; the agent backs up and replaces the user library with Filament Manager content.</li></ol></div></section>
    <div className="section-heading"><h2>Paired workstations</h2><button className="icon-button" onClick={() => void agents.refetch()} aria-label="Refresh workstations"><RefreshCw size={17} /></button></div>
    {agents.isLoading || templates.isLoading || profiles.isLoading || filaments.isLoading || printers.isLoading || plates.isLoading ? <LoadingState /> : !agents.data?.length ? <EmptyState icon={MonitorCog} title="No workstations paired" description="Create a one-time code, install the agent under your normal workstation account, and pair it with Filament Manager." /> : <div className="workstation-grid">{agents.data.map((agent) => {
      const importedTemplates = (templates.data ?? []).filter((template) => template.source_workstation_agent_id === agent.id)
      const importedProfiles = (profiles.data ?? []).filter((profile) => profile.source_workstation_agent_id === agent.id)
      const pendingImportedTemplates = importedTemplates.filter((template) => !template.active || !template.revisions.some((revision) => revision.status === 'published'))
      const pendingImportedProfiles = importedProfiles.filter((profile) => profile.status !== 'published')
      const pendingImports = pendingImportedTemplates.length + pendingImportedProfiles.length
      const selectedForAgent = agent.cura_materials.filter((material) => selectedSources.has(`${agent.id}:${material.source_id}`))
      return <article className="workstation-card card" key={agent.id}>
      <header><span className="workstation-card__icon"><MonitorCog size={22} /></span><div><h2>{agent.display_name}</h2><p>{platformLabel(agent.platform)} · {agent.hostname} · Agent {agent.agent_version}</p></div><StatusPill status={agent.enabled ? 'active' : 'disabled'} /></header>
      <dl className="definition-list"><div><dt>Cura installations</dt><dd>{agent.cura_installations.length}</dd></div><div><dt>Material library</dt><dd>{agent.cura_management_enabled ? 'Authoritative with draft edit intake' : 'Awaiting one-time takeover'}</dd></div><div><dt>Existing user materials</dt><dd>{String(agent.capabilities.unmanaged_material_count ?? 'Unknown')}</dd></div><div><dt>Agent ID</dt><dd>{agent.agent_code}</dd></div></dl>
      {agent.cura_installations.map((installation) => <div className="cura-installation" key={installation.installation_id}><strong>Cura {installation.version}</strong><small>{installation.channel} · Settings v{installation.setting_version ?? 'unknown'}</small>{installation.machines.length ? <span>{installation.machines.map((machine) => `${machine.display_name}${machine.nozzle_diameter_mm ? ` · ${machine.nozzle_diameter_mm} mm` : ''}`).join(', ')}</span> : <span>No machine instances detected</span>}</div>)}
      {!agent.cura_management_enabled ? <section className="cura-preservation" aria-label={`Cura materials reported by ${agent.display_name}`}>
        <div><h3>Select existing Cura materials</h3><p className="muted">Choose only material files you want to preserve. Use one generic source per material family as its Template profile; map branded or tuned variants to exact canonical filaments.</p></div>
        {!agent.cura_materials.length ? <p className="muted">No existing user Cura material files have been reported yet. Keep Cura closed briefly and refresh after the agent completes discovery.</p> : null}
        <div className="cura-material-list">{agent.cura_materials.map((material) => {
          const imported = importedTemplates.find((template) => template.source_cura_material_id === material.source_id)
          const importedProfile = importedProfiles.find((profile) => profile.source_cura_material_id === material.source_id)
          const preserved = Boolean(imported?.active && imported.revisions.some((revision) => revision.status === 'published')) || importedProfile?.status === 'published'
          const sourceKey = `${agent.id}:${material.source_id}`
          return <article className="cura-material-item" key={`${material.installation_id}:${material.source_id}`}>
            <label className="cura-material-choice"><input type="checkbox" checked={selectedSources.has(sourceKey)} disabled={Boolean(imported || importedProfile) || user?.role !== 'administrator'} onChange={(event) => setSelectedSources((current) => { const next = new Set(current); if (event.target.checked) next.add(sourceKey); else next.delete(sourceKey); return next })} /><span><strong>{material.name}</strong><small>{material.brand} · {material.material_type} · {Object.keys(material.settings).length} approved settings</small></span></label>
            {preserved ? <div className="cura-material-item__status"><StatusPill status="published" /><Link className="button button--small" to={imported ? '/templates' : '/profiles'}>View {imported ? 'template' : 'profile'}</Link></div> : imported || importedProfile ? <div className="cura-material-item__status"><StatusPill status="draft" /><Link className="button button--small" to={imported ? '/templates' : '/profiles'}>Review and publish</Link></div> : <span className="muted">Not imported</span>}
          </article>
        })}</div>
        {selectedForAgent.length && user?.role === 'administrator' && printers.data?.length ? <button className="button button--primary" type="button" onClick={() => openTemplateImport(agent, selectedForAgent[0])}><FileInput size={15} /> Review selected imports ({selectedForAgent.length})</button> : null}
        {pendingImports ? <p className="form-error" role="status">Publish {pendingImports} imported draft{pendingImports === 1 ? '' : 's'} before managing and synchronizing this workstation.</p> : null}
      </section> : null}
      {user?.role === 'administrator' && <div className="template-card__actions"><button className="button" disabled={synchronizeCura.isPending || pendingImports > 0} onClick={() => {
        if (pendingImports) {
          setMessage('Review and publish every imported Cura template and profile before managing this workstation.')
          return
        }
        if (!agent.cura_management_enabled && !window.confirm('Filament Manager will back up and replace every user material file in each detected Cura version, then hide Cura bundled materials in the selectors. Continue?')) return
        synchronizeCura.mutate(agent)
      }}><Library size={16} />{agent.cura_management_enabled ? 'Synchronize library' : 'Manage and synchronize Cura'}</button><button className="button" disabled={toggleAgent.isPending} onClick={() => toggleAgent.mutate(agent)}>{agent.enabled ? <PowerOff size={16} /> : <Power size={16} />}{agent.enabled ? 'Revoke agent' : 'Enable agent'}</button></div>}
    </article>})}</div>}
    {importSelection ? <Modal title="Preserve selected Cura material" description="Choose whether this source becomes the one family template or a filament-specific profile. No workstation files change until takeover." onClose={() => setImportSelection(null)} size="wide" footer={<><button className="button" type="button" onClick={() => setImportSelection(null)}>Cancel</button><button className="button button--primary" type="submit" form="import-cura-template" disabled={importMaterial.isPending}><FileInput size={16} />{importMaterial.isPending ? 'Importing…' : 'Import draft'}</button></>}>
      <form id="import-cura-template" className="editor-form" onSubmit={(event) => {
        event.preventDefault()
        const data = new FormData(event.currentTarget)
        const common = {
          agent_id: importSelection.agent.id,
          source_id: importSelection.material.source_id,
          printer_id: importPrinterId,
          nozzle_diameter_mm: importNozzleDiameter,
          preferred_build_plate_surface_id: String(data.get('preferred_build_plate_surface_id') ?? '') || null,
        }
        importMaterial.mutate({ target: importTarget, payload: importTarget === 'template' ? {
          ...common,
          name: `Template ${String(data.get('material_type') ?? '').trim()}`,
          material_type: String(data.get('material_type') ?? '').trim(),
          description: String(data.get('description') ?? '').trim() || null,
          filament_diameter_mm: String(data.get('filament_diameter_mm') ?? ''),
          filament_density_g_cm3: String(data.get('filament_density_g_cm3') ?? ''),
        } : { ...common, filament_product_id: importFilamentId } })
      }}>
        <EditorSection title="Cura source" description="Only the approved material-scoped settings already reported by the workstation are copied.">
          <dl className="definition-list"><div><dt>Material</dt><dd>{importSelection.material.name}</dd></div><div><dt>Workstation</dt><dd>{importSelection.agent.display_name}</dd></div><div><dt>Approved settings</dt><dd>{Object.keys(importSelection.material.settings).length}</dd></div></dl>
        </EditorSection>
        <EditorSection title="Draft template identity" description="Choose the generic material family and the exact printer/nozzle scope to preserve.">
          <div className="segmented-control" role="radiogroup" aria-label="Import destination"><button type="button" className={importTarget === 'template' ? 'active' : ''} onClick={() => setImportTarget('template')}>Family template</button><button type="button" className={importTarget === 'profile' ? 'active' : ''} onClick={() => setImportTarget('profile')}>Filament profile</button></div>
          <div className="form-grid">
            {importTarget === 'template' ? <label>Material type<input name="material_type" defaultValue={importSelection.material.material_type} required autoFocus /><small className="field-help">Saved as Template {importSelection.material.material_type} under the Template brand in Cura.</small></label> : <label>Canonical filament<select value={importFilamentId} onChange={(event) => setImportFilamentId(event.target.value)} required autoFocus>{filaments.data?.map((filament) => <option key={filament.id} value={filament.id}>{[filament.vendor_name, filament.material_type, filament.color_name].filter(Boolean).join(' · ')}</option>)}</select><small className="field-help">The filament must already link to the published family template for this scope.</small></label>}
            <label>Printer<select name="printer_id" value={importPrinterId} required onChange={(event) => {
              const selected = printers.data?.find((printer) => printer.id === event.target.value)
              setImportPrinterId(event.target.value)
              setImportNozzleDiameter(selected?.nozzle_diameter_mm ?? '0.4')
            }}>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label>
            <label>Nozzle diameter<input name="nozzle_diameter_mm" type="number" min="0.1" step="0.05" value={importNozzleDiameter} onChange={(event) => setImportNozzleDiameter(event.target.value)} required /></label>
            {importTarget === 'template' ? <><label>Filament diameter<input name="filament_diameter_mm" type="number" min="0.1" step="0.01" defaultValue="1.75" required /></label><label>Filament density<input name="filament_density_g_cm3" type="number" min="0.01" step="0.001" placeholder="1.24" required /></label></> : null}
            <label className="form-grid__wide">Preferred plate side<select name="preferred_build_plate_surface_id"><option value="">No preference</option>{plates.data?.flatMap((plate) => plate.surfaces.map((surface) => <option key={surface.id} value={surface.id}>{surface.surface_code} · {surface.surface_material ?? 'Surface not specified'}</option>))}</select></label>
            {importTarget === 'template' ? <label className="form-grid__wide">Description<textarea name="description" rows={2} placeholder="Import source and review notes" /></label> : null}
          </div>
        </EditorSection>
        {importMaterial.error ? <p className="form-error" role="alert">{importMaterial.error.message}</p> : null}
      </form>
    </Modal> : null}
  </div>
}
