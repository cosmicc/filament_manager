import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Clipboard, MonitorCog, Power, PowerOff, RefreshCw, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import type { CuraMaterialReport, MaterialTemplate, Printer, WorkstationAgent, WorkstationPairingCode } from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime } from '../lib/format'

function platformLabel(platform: WorkstationAgent['platform']) {
  return platform === 'windows_11' ? 'Windows 11' : 'Arch Linux'
}

function sourceType(material: CuraMaterialReport) {
  return material.source_kind === 'print_profile' ? 'Saved print profile' : 'Material profile'
}

function sourceDetails(material: CuraMaterialReport) {
  if (material.source_kind === 'print_profile') {
    return [material.machine_name, material.quality_type, `${Object.keys(material.settings).length} tracked settings`]
      .filter(Boolean)
      .join(' · ')
  }
  return `${material.brand} · ${material.material_type} · ${Object.keys(material.settings).length} tracked settings`
}

export default function WorkstationsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [pairing, setPairing] = useState<WorkstationPairingCode | null>(null)
  const [copied, setCopied] = useState(false)
  const [mappings, setMappings] = useState<Record<string, string>>({})
  const [takeoverAgent, setTakeoverAgent] = useState<WorkstationAgent | null>(null)
  const [takeoverStep, setTakeoverStep] = useState<'mapping' | 'review'>('mapping')
  const [message, setMessage] = useState('')
  const agents = useQuery({ queryKey: ['workstation-agents'], queryFn: () => apiFetch<WorkstationAgent[]>('/workstation-agents'), refetchInterval: 15_000 })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=true'), refetchInterval: 15_000 })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
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
  const takeover = useMutation({
    mutationFn: (agent: WorkstationAgent) => apiFetch<WorkstationAgent>(`/workstation-agents/${agent.id}/cura-takeover`, {
      method: 'POST',
      body: JSON.stringify({
        expected_agent_version: agent.record_version,
        confirmed: true,
        mappings: agent.cura_materials
          .map((source) => ({ source_id: source.source_id, template_id: mappings[`${agent.id}:${source.source_id}`] }))
          .filter((mapping) => Boolean(mapping.template_id)),
      }),
    }),
    onSuccess: async (_, agent) => {
      const mappedCount = agent.cura_materials.filter((source) => mappings[`${agent.id}:${source.source_id}`]).length
      setMessage(`Cura takeover completed with ${mappedCount} imported source${mappedCount === 1 ? '' : 's'}. Automatic synchronization is active.`)
      setTakeoverAgent(null)
      setTakeoverStep('mapping')
      setMappings((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${agent.id}:`))))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workstation-agents'] }),
        queryClient.invalidateQueries({ queryKey: ['material-templates'] }),
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
        queryClient.invalidateQueries({ queryKey: ['diagnostics'] }),
      ])
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const activeTemplates = useMemo(() => (templates.data ?? []).filter((template) => template.active && template.revisions.length > 0), [templates.data])
  const currentTakeoverAgent = takeoverAgent
    ? agents.data?.find((agent) => agent.id === takeoverAgent.id) ?? takeoverAgent
    : null
  const printerName = (printerId: string) => printers.data?.find((printer) => printer.id === printerId)?.name ?? 'Unknown printer'
  const templateLabel = (template: MaterialTemplate) => `${template.name} · ${printerName(template.printer_id)} · ${template.nozzle_diameter_mm} mm`
  const openTakeover = (agent: WorkstationAgent) => {
    setMessage('')
    setTakeoverAgent(agent)
    setTakeoverStep('mapping')
  }
  const copyPairing = async () => {
    if (!pairing) return
    await navigator.clipboard.writeText(pairing.pairing_code)
    setCopied(true)
  }

  return <div>
    <PageHeader eyebrow="Cura automation" title="Cura workstations" description="Complete one reviewed takeover, then Filament Manager keeps Cura synchronized automatically. Changes to known managed materials save directly; new materials are added in Filament Manager." actions={user?.role === 'administrator' ? <button className="button button--primary" onClick={() => createPairing.mutate()} disabled={createPairing.isPending}><ShieldCheck size={17} /> Create pairing code</button> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    {pairing && <section className="pairing-card card" aria-live="polite">
      <div><h2>Pairing code</h2><p>Valid until {dateTime(pairing.expires_at)}. It can enroll one workstation and is never shown again.</p></div>
      <div className="pairing-code"><code>{pairing.pairing_code}</code><button className="icon-button" onClick={() => void copyPairing()} aria-label="Copy pairing code">{copied ? <Check size={18} /> : <Clipboard size={18} />}</button></div>
      <p className="muted">On that workstation, install the agent and run <code>filament-manager-agent pair --server https://your-filament-manager.example --name &quot;Cura workstation&quot;</code>. Paste the code only at the hidden prompt.</p>
    </section>}
    {createPairing.error && <div className="form-error">{createPairing.error.message}</div>}
    <section className="card diagnostic-actions cura-takeover-guide"><div><p className="eyebrow">One-time takeover</p><h2>Choose what becomes each template</h2><ol><li>Pair the workstation and wait for Cura discovery.</li><li>For each Cura source you want to keep, choose its existing Filament Manager template. Leave sources you do not want as Do not import.</li><li>Review all mappings together and confirm once.</li><li>The agent backs up and replaces the user material library, hides bundled materials, and starts automatic synchronization.</li></ol></div></section>
    <div className="section-heading"><h2>Paired workstations</h2><button className="icon-button" onClick={() => void agents.refetch()} aria-label="Refresh workstations"><RefreshCw size={17} /></button></div>
    {agents.isLoading || templates.isLoading || printers.isLoading ? <LoadingState /> : !agents.data?.length ? <EmptyState icon={MonitorCog} title="No workstations paired" description="Create a one-time code, install the agent under your normal workstation account, and pair it with Filament Manager." /> : <div className="workstation-grid">{agents.data.map((agent) => {
      return <article className="workstation-card card" key={agent.id}>
        <header><span className="workstation-card__icon"><MonitorCog size={22} /></span><div><h2>{agent.display_name}</h2><p>{platformLabel(agent.platform)} · {agent.hostname} · Agent {agent.agent_version}</p></div><StatusPill status={agent.enabled ? 'active' : 'disabled'} /></header>
        <dl className="definition-list"><div><dt>Cura installations</dt><dd>{agent.cura_installations.length}</dd></div><div><dt>Material library</dt><dd>{agent.cura_management_enabled ? 'Automatic synchronization active' : 'Awaiting one-time takeover'}</dd></div><div><dt>Existing material profiles</dt><dd>{String(agent.capabilities.unmanaged_material_count ?? 'Unknown')}</dd></div><div><dt>Saved print profiles</dt><dd>{String(agent.capabilities.unmanaged_print_profile_count ?? 'Unknown')}</dd></div><div><dt>Agent ID</dt><dd>{agent.agent_code}</dd></div></dl>
        {agent.cura_installations.map((installation) => <div className="cura-installation" key={installation.installation_id}><strong>Cura {installation.version}</strong><small>{installation.channel} · Settings v{installation.setting_version ?? 'unknown'}</small>{installation.machines.length ? <span>{installation.machines.map((machine) => `${machine.display_name}${machine.nozzle_diameter_mm ? ` · ${machine.nozzle_diameter_mm} mm` : ''}`).join(', ')}</span> : <span>No machine instances detected</span>}</div>)}
        {!agent.cura_management_enabled ? <section className="cura-preservation" aria-label={`Cura sources reported by ${agent.display_name}`}>
          <div><h3>Import Cura profiles into templates</h3><p className="muted">Choose each Cura source from a list and map it to one existing template. Sources you leave unmapped will be discarded only after backup.</p></div>
          <dl className="definition-list definition-list--compact"><div><dt>Selectable Cura sources</dt><dd>{agent.cura_materials.length}</dd></div><div><dt>Available templates</dt><dd>{activeTemplates.length}</dd></div></dl>
          {!agent.cura_materials.length ? <p className="warning-note">No selectable Cura profiles have been reported yet. Upgrade or restart the workstation agent, keep Cura closed, then refresh this page before completing takeover.</p> : null}
          {user?.role === 'administrator' ? <button className="button button--primary" type="button" disabled={!agent.enabled || !agent.cura_installations.length || takeover.isPending} onClick={() => openTakeover(agent)}>{agent.cura_materials.length ? 'Map Cura profiles' : 'Review empty takeover'}</button> : null}
        </section> : <p className="success-note">Filament Manager owns this Cura material library. Direct saves in either application synchronize automatically.</p>}
        {user?.role === 'administrator' && <div className="template-card__actions"><button className="button" disabled={toggleAgent.isPending} onClick={() => toggleAgent.mutate(agent)}>{agent.enabled ? <PowerOff size={16} /> : <Power size={16} />}{agent.enabled ? 'Revoke agent' : 'Enable agent'}</button></div>}
      </article>
    })}</div>}
    {currentTakeoverAgent ? <Modal title={takeoverStep === 'mapping' ? 'Map Cura profiles to templates' : 'Review Cura takeover'} description={takeoverStep === 'mapping' ? 'Select the destination template for every Cura profile you want to keep. Do not import is intentional and remains the default.' : 'This is the one confirmation for all source-to-template choices. The operation is atomic: either every mapping and synchronization state saves, or none do.'} onClose={() => setTakeoverAgent(null)} size="wide" footer={takeoverStep === 'mapping' ? <><button className="button" type="button" onClick={() => setTakeoverAgent(null)}>Cancel</button><button className="button button--primary" type="button" onClick={() => setTakeoverStep('review')}>Review takeover ({currentTakeoverAgent.cura_materials.filter((source) => mappings[`${currentTakeoverAgent.id}:${source.source_id}`]).length} mapped)</button></> : <><button className="button" type="button" onClick={() => setTakeoverStep('mapping')}>Back to mappings</button><button className="button button--primary" type="button" disabled={takeover.isPending} onClick={() => takeover.mutate(currentTakeoverAgent)}><ShieldCheck size={16} />{takeover.isPending ? 'Completing…' : 'Complete takeover'}</button></>}>
      {takeoverStep === 'mapping' ? <>
        <EditorSection title="Cura profiles" description="Only settings tracked by Filament Manager are imported. Each source and template can be selected once.">
          {currentTakeoverAgent.cura_materials.length ? <div className="cura-material-list">{currentTakeoverAgent.cura_materials.map((source) => {
            const key = `${currentTakeoverAgent.id}:${source.source_id}`
            const selectedTemplate = mappings[key] ?? ''
            const selectedTemplateIds = new Set(currentTakeoverAgent.cura_materials.map((item) => mappings[`${currentTakeoverAgent.id}:${item.source_id}`]).filter(Boolean))
            return <article className="cura-material-item" key={`${source.installation_id}:${source.source_id}`}>
              <div className="cura-material-choice"><span><strong>{source.name}</strong><small>{sourceType(source)} · {sourceDetails(source)}</small>{source.omitted_setting_count ? <small>{source.omitted_setting_count} Cura expression{source.omitted_setting_count === 1 ? '' : 's'} omitted safely</small> : null}</span></div>
              <label>Import into template<select aria-label={`Template for ${source.name}`} value={selectedTemplate} onChange={(event) => setMappings((current) => ({ ...current, [key]: event.target.value }))}><option value="">Do not import</option>{activeTemplates.map((template) => <option key={template.id} value={template.id} disabled={template.id !== selectedTemplate && selectedTemplateIds.has(template.id)}>{templateLabel(template)}</option>)}</select></label>
            </article>
          })}</div> : <div className="warning-note"><strong>No Cura profiles are selectable.</strong> Upgrade or restart the workstation agent and wait for its next check-in. Complete an empty takeover only when Cura truly contains nothing you want to import.</div>}
        </EditorSection>
      </> : <>
      <EditorSection title="Sources to import" description="Each selected source directly updates the current settings of its mapped template. Linked filament profiles inherit those changes immediately except for explicitly customized values.">
        {currentTakeoverAgent.cura_materials.some((source) => mappings[`${currentTakeoverAgent.id}:${source.source_id}`]) ? <div className="comparison-table">{currentTakeoverAgent.cura_materials.filter((source) => mappings[`${currentTakeoverAgent.id}:${source.source_id}`]).map((source) => {
          const template = activeTemplates.find((item) => item.id === mappings[`${currentTakeoverAgent.id}:${source.source_id}`])
          return <div className="comparison-row" key={source.source_id}><div className="comparison-setting"><strong>{source.name}</strong><small>{sourceType(source)}</small></div><div className="comparison-value">{template ? templateLabel(template) : 'Template unavailable'}</div></div>
        })}</div> : <p className="muted">No Cura sources will be imported.</p>}
      </EditorSection>
      <EditorSection title="Sources to discard" description="Unmapped sources are not added to Filament Manager and are removed from the managed Cura library after backup.">
        <p>{currentTakeoverAgent.cura_materials.filter((source) => !mappings[`${currentTakeoverAgent.id}:${source.source_id}`]).length} of {currentTakeoverAgent.cura_materials.length} reported sources will not be imported.</p>
      </EditorSection>
      <div className="warning-note"><strong>Takeover changes Cura files.</strong> The workstation agent waits for Cura to close, backs up affected user files, replaces the library atomically, and hides bundled materials. Machine, quality, and start/end G-code configuration remain unchanged.</div>
      {takeover.error ? <p className="form-error" role="alert">{takeover.error.message}</p> : null}
      </>}
    </Modal> : null}
  </div>
}
