import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Clipboard, DatabaseBackup, MonitorCog, Power, PowerOff, RefreshCw, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { CuraDeployment, CuraMaterialSettingsSyncReport, WorkstationAgent, WorkstationPairingCode } from '../api/types'
import { CuraRecoveryModal } from '../components/CuraRecoveryModal'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { compactNumber, dateTime } from '../lib/format'

function platformLabel(platform: WorkstationAgent['platform']) {
  return platform === 'windows_11' ? 'Windows 11' : 'Arch Linux'
}

function recoveryLabel(status: string | undefined) {
  if (status === 'ready') return 'Recovery ready'
  if (status === 'capture_blocked') return 'Last good recovery preserved'
  if (status === 'restore_pending') return 'Waiting for Cura to close'
  if (status === 'restoring') return 'Restoring Cura'
  if (status === 'restore_failed') return 'Recovery failed'
  return 'Waiting for first recovery point'
}

function materialSettingsSummary(sync: CuraMaterialSettingsSyncReport | null | undefined) {
  if (!sync) return {
    status: 'warning',
    label: 'Verification unavailable',
    detail: 'Upgrade and restart the workstation agent, then open Cura once.',
  }
  const pluginVersions = (sync.plugins ?? [])
    .map((plugin) => `${plugin.display_name} ${plugin.version}${plugin.enabled ? '' : ' (disabled)'}`)
    .join(' · ')
  if (sync.status === 'healthy') return {
    status: 'healthy',
    label: `${sync.exposed_count} of ${sync.expected_count} verified`,
    detail: `Material Settings and Klipper Settings are ready; managed values are enforced over Cura profiles.${pluginVersions ? ` ${pluginVersions}.` : ''}`,
  }
  if (['waiting_for_cura', 'waiting_for_machine', 'not_deployed'].includes(sync.status)) return {
    status: 'warning',
    label: 'Waiting for Cura',
    detail: `${sync.expected_count} settings are deployed. Open or restart Cura with this printer active to verify them.`,
  }
  if (sync.status === 'invalid') return {
    status: 'error',
    label: 'Invalid verification receipt',
    detail: 'Upgrade and restart the workstation agent and Cura to regenerate the receipt.',
  }
  const missing = sync.missing_keys.slice(0, 8).join(', ')
  return {
    status: 'error',
    label: `${sync.exposed_count} of ${sync.expected_count} exposed`,
    detail: `Missing: ${missing || 'none reported'}. Material Settings: ${sync.material_settings_plugin_ready ? 'ready' : 'not ready'}; Klipper Settings: ${sync.klipper_settings_plugin_ready ? 'ready' : 'not ready'}.`,
  }
}

export default function WorkstationsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [pairing, setPairing] = useState<WorkstationPairingCode | null>(null)
  const [copied, setCopied] = useState(false)
  const [takeoverAgent, setTakeoverAgent] = useState<WorkstationAgent | null>(null)
  const [recoveryAgent, setRecoveryAgent] = useState<WorkstationAgent | null>(null)
  const [message, setMessage] = useState('')
  const agents = useQuery({ queryKey: ['workstation-agents'], queryFn: () => apiFetch<WorkstationAgent[]>('/workstation-agents'), refetchInterval: 15_000 })
  const [syncRequests, setSyncRequests] = useState<Record<string, string>>({})
  const deployments = useQuery({ queryKey: ['cura-deployments'], queryFn: () => apiFetch<CuraDeployment[]>('/cura-deployments'), refetchInterval: (query) => Object.values(syncRequests).some((id) => {
    const status = query.state.data?.find((item) => item.id === id)?.status
    return !status || status === 'pending' || status === 'claimed'
  }) ? 5000 : false, enabled: Object.keys(syncRequests).length > 0 })
  const sync = useMutation({
    mutationFn: (agent: WorkstationAgent) => apiFetch<CuraDeployment[]>(`/workstation-agents/${agent.id}/sync`, { method: 'POST' }),
    onSuccess: (items, agent) => {
      queryClient.setQueryData<CuraDeployment[]>(['cura-deployments'], (current = []) => [...items, ...current.filter((item) => !items.some((updated) => updated.id === item.id))])
      setSyncRequests((current) => ({ ...current, [agent.id]: items[0].id }))
      setMessage(`App settings queued for ${agent.display_name}. Close Cura and wait for Succeeded before reopening; an offline agent must reconnect first.`)
      void queryClient.invalidateQueries({ queryKey: ['cura-deployments'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
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
        reviewed_source_ids: [...new Set(agent.cura_materials.map((source) => source.source_id))],
        confirmed: true,
        mappings: [],
      }),
    }),
    onSuccess: async () => {
      setMessage("App-owned Cura synchronization enabled. Close Cura and wait for synchronization before reopening.")
      setTakeoverAgent(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workstation-agents'] }),
        queryClient.invalidateQueries({ queryKey: ['material-templates'] }),
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
        queryClient.invalidateQueries({ queryKey: ['diagnostics'] }),
      ])
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const currentTakeoverAgent = takeoverAgent
    ? agents.data?.find((agent) => agent.id === takeoverAgent.id) ?? takeoverAgent
    : null
  const openTakeover = (agent: WorkstationAgent) => {
    setMessage('')
    setTakeoverAgent(agent)
  }
  const copyPairing = async () => {
    if (!pairing) return
    await navigator.clipboard.writeText(pairing.pairing_code)
    setCopied(true)
  }

  return <div>
    <PageHeader eyebrow="Cura automation" title="Cura workstations" description="Keep managed materials synchronized and retain safe, versioned Cura printer and settings recovery points. All tracked print settings are edited only in Filament Manager and sent one-way to Cura." actions={user?.role === 'administrator' ? <button className="button button--primary" onClick={() => createPairing.mutate()} disabled={createPairing.isPending}><ShieldCheck size={17} /> Add Cura workstation</button> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    {deployments.error ? <div className="form-error" role="alert">Unable to confirm synchronization status: {deployments.error.message}</div> : null}
    {pairing && <section className="pairing-card card" aria-live="polite">
      <div><h2>Pairing code</h2><p>Valid until {dateTime(pairing.expires_at)}. It can enroll one workstation and is never shown again.</p></div>
      <div className="pairing-code"><code>{pairing.pairing_code}</code><button className="icon-button" onClick={() => void copyPairing()} aria-label="Copy pairing code">{copied ? <Check size={18} /> : <Clipboard size={18} />}</button></div>
      <p className="muted">On that workstation, install the agent and run <code>filament-manager-agent pair --server https://your-filament-manager.example --name &quot;Cura workstation&quot;</code>. Paste the code only at the hidden prompt.</p>
    </section>}
    {createPairing.error && <div className="form-error">{createPairing.error.message}</div>}
    <section className="card diagnostic-actions cura-takeover-guide"><div><p className="eyebrow">App-owned settings</p><h2>Filament Manager → Cura</h2><p>Edit templates and filament settings here, then use Push app settings. Close Cura and wait for the sync to succeed before reopening. Offline agents receive the request on their next check-in. Cura changes are never imported.</p></div></section>
    <div className="section-heading"><h2>Paired workstations</h2><button className="icon-button" onClick={() => void agents.refetch()} aria-label="Refresh workstations"><RefreshCw size={17} /></button></div>
    {agents.isLoading ? <LoadingState /> : !agents.data?.length ? <EmptyState icon={MonitorCog} title="No workstations paired" description="Create a one-time code, install the agent under your normal workstation account, and pair it with Filament Manager." /> : <div className="workstation-grid">{agents.data.map((agent) => {
      return <article className="workstation-card card" key={agent.id}>
        <header><span className="workstation-card__icon"><MonitorCog size={22} /></span><div><h2>{agent.display_name}</h2><p>{platformLabel(agent.platform)} · {agent.hostname} · Agent {agent.agent_version}</p></div><StatusPill status={agent.enabled ? 'active' : 'disabled'} /></header>
        <dl className="definition-list"><div><dt>Cura installations</dt><dd>{agent.cura_installations.length}</dd></div><div><dt>Material library</dt><dd>{agent.cura_management_enabled ? 'Automatic synchronization active' : 'Awaiting one-time takeover'}</dd></div><div><dt>{agent.cura_management_enabled ? 'Managed material profiles' : 'Unmanaged material import sources'}</dt><dd>{String(agent.cura_management_enabled ? agent.capabilities.managed_material_count ?? 'Unknown' : agent.capabilities.unmanaged_material_count ?? 'Unknown')}</dd></div><div><dt>User-saved custom print profiles</dt><dd>{String(agent.capabilities.unmanaged_print_profile_count ?? 'Unknown')}</dd></div><div><dt>Agent ID</dt><dd>{agent.agent_code}</dd></div></dl>
        {agent.cura_installations.map((installation) => {
          const settingsSummary = materialSettingsSummary(installation.material_settings_sync)
          return <div className="cura-installation" key={installation.installation_id}>
            <strong>Cura {installation.version}</strong>
            <small>{installation.channel} · Settings v{installation.setting_version ?? 'unknown'}</small>
            {installation.machines.length ? <span>{installation.machines.map((machine) => `${machine.display_name}${machine.nozzle_diameter_mm ? ` · ${compactNumber(machine.nozzle_diameter_mm, 1)} mm` : ''}`).join(', ')}</span> : <span>No machine instances detected</span>}
            {agent.cura_management_enabled ? <div className="cura-material-settings-status">
              <span><ShieldCheck size={16} /><strong>Material print settings</strong></span>
              <StatusPill status={settingsSummary.status} label={settingsSummary.label} />
              <small>{settingsSummary.detail}</small>
              {installation.material_settings_sync?.verified_at ? <small>Verified {dateTime(installation.material_settings_sync.verified_at)}</small> : null}
            </div> : null}
          </div>
        })}
        <section className="cura-recovery-summary" aria-label={`Cura recovery for ${agent.display_name}`}>
          <div><span className="workstation-card__icon"><DatabaseBackup size={19} /></span><span><strong>Cura recovery</strong><small>{agent.last_recovery_snapshot_at ? `Latest snapshot ${dateTime(agent.last_recovery_snapshot_at)}` : 'No recovery point captured yet'}</small></span><StatusPill status={agent.cura_recovery_status ?? 'not_ready'} label={recoveryLabel(agent.cura_recovery_status)} /></div>
          {agent.cura_recovery_message ? <p className={agent.cura_recovery_status === 'restore_failed' ? 'form-error' : 'muted'}>{agent.cura_recovery_message}</p> : null}
          {agent.last_error ? <p className="form-error" role="alert"><strong>Workstation agent:</strong> {agent.last_error}</p> : null}
          {agent.capabilities.cura_recovery_snapshots !== true ? <p className="warning-note">Upgrade this workstation agent to enable automatic printer and settings recovery.</p> : null}
          {user?.role === 'administrator' ? <button className="button" type="button" disabled={agent.capabilities.cura_recovery_snapshots !== true} onClick={() => setRecoveryAgent(agent)}><DatabaseBackup size={16} /> Recovery points</button> : null}
        </section>
        {!agent.cura_management_enabled ? <section className="cura-preservation">
          <h3>Enable app-owned Cura settings</h3><p>The agent backs up and replaces user materials with app values. No Cura settings will be imported.</p>
          {user?.role === 'administrator' ? <button className="button button--primary" disabled={!agent.enabled || !agent.cura_installations.length || takeover.isPending} onClick={() => openTakeover(agent)}>Review takeover</button> : null}
        </section> : <p className="success-note">Filament Manager owns all tracked settings. Changes made in Cura never update the app.</p>}
        {agent.cura_management_enabled && user?.role === 'administrator' ? <div className="template-card__actions">
          <button className="button button--primary" disabled={!agent.enabled || !agent.cura_installations.length || sync.isPending} onClick={() => sync.mutate(agent)}><RefreshCw size={16} />Push app settings</button>
          {syncRequests[agent.id] ? <StatusPill status={deployments.data?.find((item) => item.id === syncRequests[agent.id])?.status ?? 'pending'} /> : null}
        </div> : null}
        {user?.role === 'administrator' && <div className="template-card__actions"><button className="button" disabled={toggleAgent.isPending} onClick={() => toggleAgent.mutate(agent)}>{agent.enabled ? <PowerOff size={16} /> : <Power size={16} />}{agent.enabled ? 'Revoke agent' : 'Enable agent'}</button></div>}
      </article>
    })}</div>}
    {currentTakeoverAgent ? <Modal title="Review Cura takeover" description="The app is the sole source of tracked print settings." onClose={() => setTakeoverAgent(null)} footer={<><button className="button" onClick={() => setTakeoverAgent(null)}>Cancel</button><button className="button button--primary" disabled={takeover.isPending} onClick={() => takeover.mutate(currentTakeoverAgent)}>Complete takeover</button></>}>
      <p>No Cura settings will be imported. Existing user materials are backed up and replaced; bundled materials are hidden. App-owned start/end G-code is installed, while unrelated Cura quality settings remain workstation-owned.</p>
      <p>Close Cura before synchronization and wait for completion before reopening.</p>
      {takeover.error ? <p className="form-error" role="alert">{takeover.error.message}</p> : null}
    </Modal> : null}
    {recoveryAgent ? <CuraRecoveryModal agent={recoveryAgent} agents={agents.data ?? []} onClose={() => setRecoveryAgent(null)} onQueued={setMessage} /> : null}
  </div>
}
