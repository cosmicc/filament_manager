import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Clipboard, MonitorCog, Power, PowerOff, RefreshCw, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { CuraDeployment, WorkstationAgent, WorkstationPairingCode } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime } from '../lib/format'

function platformLabel(platform: WorkstationAgent['platform']) {
  return platform === 'windows_11' ? 'Windows 11' : 'Arch Linux'
}

export default function WorkstationsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [pairing, setPairing] = useState<WorkstationPairingCode | null>(null)
  const [copied, setCopied] = useState(false)
  const agents = useQuery({ queryKey: ['workstation-agents'], queryFn: () => apiFetch<WorkstationAgent[]>('/workstation-agents'), refetchInterval: 15_000 })
  const deployments = useQuery({ queryKey: ['cura-deployments'], queryFn: () => apiFetch<CuraDeployment[]>('/cura-deployments'), refetchInterval: 10_000 })
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
  const copyPairing = async () => {
    if (!pairing) return
    await navigator.clipboard.writeText(pairing.pairing_code)
    setCopied(true)
  }
  return <div>
    <PageHeader eyebrow="Cura automation" title="Cura workstations" description="Pair an outbound-only agent on each Arch Linux or Windows 11 workstation, then deploy published profiles everywhere from one button." actions={user?.role === 'administrator' ? <button className="button button--primary" onClick={() => createPairing.mutate()} disabled={createPairing.isPending}><ShieldCheck size={17} /> Create pairing code</button> : undefined} />
    {pairing && <section className="pairing-card card" aria-live="polite">
      <div><h2>Pairing code</h2><p>Valid until {dateTime(pairing.expires_at)}. It can enroll one workstation and is never shown again.</p></div>
      <div className="pairing-code"><code>{pairing.pairing_code}</code><button className="icon-button" onClick={() => void copyPairing()} aria-label="Copy pairing code">{copied ? <Check size={18} /> : <Clipboard size={18} />}</button></div>
      <p className="muted">On that workstation, install the agent and run <code>filament-manager-agent pair --server https://your-filament-manager.example --name &quot;Cura workstation&quot;</code>. Paste the code only at the hidden prompt.</p>
    </section>}
    {createPairing.error && <div className="form-error">{createPairing.error.message}</div>}
    <div className="section-heading"><h2>Paired workstations</h2><button className="icon-button" onClick={() => void agents.refetch()} aria-label="Refresh workstations"><RefreshCw size={17} /></button></div>
    {agents.isLoading ? <LoadingState /> : !agents.data?.length ? <EmptyState icon={MonitorCog} title="No workstations paired" description="Create a one-time code, install the agent under your normal workstation account, and pair it with Filament Manager." /> : <div className="workstation-grid">{agents.data.map((agent) => <article className="workstation-card card" key={agent.id}>
      <header><span className={`health-dot ${agent.enabled && agent.last_seen_at ? 'health-dot--connected' : 'health-dot--disabled'}`} /><div><h2>{agent.display_name}</h2><p>{platformLabel(agent.platform)} · {agent.hostname} · Agent {agent.agent_version}</p></div><StatusPill status={agent.enabled ? 'active' : 'disabled'} /></header>
      <dl className="definition-list"><div><dt>Last contact</dt><dd>{agent.last_seen_at ? dateTime(agent.last_seen_at) : 'Never'}</dd></div><div><dt>Cura installations</dt><dd>{agent.cura_installations.length}</dd></div><div><dt>Agent ID</dt><dd>{agent.agent_code}</dd></div></dl>
      {agent.cura_installations.map((installation) => <div className="cura-installation" key={installation.installation_id}><strong>Cura {installation.version}</strong><small>{installation.channel} · Settings v{installation.setting_version ?? 'unknown'}</small>{installation.machines.length ? <span>{installation.machines.map((machine) => `${machine.display_name}${machine.nozzle_diameter_mm ? ` · ${machine.nozzle_diameter_mm} mm` : ''}`).join(', ')}</span> : <span>No machine instances detected</span>}</div>)}
      {agent.last_error && <p className="form-error">{agent.last_error}</p>}
      {user?.role === 'administrator' && <button className="button" disabled={toggleAgent.isPending} onClick={() => toggleAgent.mutate(agent)}>{agent.enabled ? <PowerOff size={16} /> : <Power size={16} />}{agent.enabled ? 'Revoke agent' : 'Enable agent'}</button>}
    </article>)}</div>}
    <div className="section-heading"><h2>Recent deployments</h2></div>
    {deployments.isLoading ? <LoadingState /> : !deployments.data?.length ? <EmptyState icon={RefreshCw} title="No Cura deployments yet" description="Open Material profiles and deploy a published profile to every active workstation." /> : <div className="table-card"><table><thead><tr><th>Workstation</th><th>Status</th><th>Attempts</th><th>Requested</th><th>Completed</th><th>Detail</th></tr></thead><tbody>{deployments.data.map((deployment) => <tr key={deployment.id}><td>{agents.data?.find((item) => item.id === deployment.agent_id)?.display_name ?? deployment.agent_id.slice(0, 8)}</td><td><StatusPill status={deployment.status} /></td><td>{deployment.attempts}</td><td>{dateTime(deployment.created_at)}</td><td>{deployment.completed_at ? dateTime(deployment.completed_at) : '—'}</td><td>{deployment.last_error_message ?? (deployment.status === 'succeeded' ? 'Installed with automatic backup' : 'Waiting for agent')}</td></tr>)}</tbody></table></div>}
  </div>
}
