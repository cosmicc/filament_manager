import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseBackup, RotateCcw, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { CuraRecoveryRestore, CuraRecoverySnapshot, WorkstationAgent } from '../api/types'
import { dateTime } from '../lib/format'
import { EditorSection } from './EditorSection'
import { EmptyState } from './EmptyState'
import { LoadingState } from './LoadingState'
import { Modal } from './Modal'

function fileSize(value: number) {
  if (value < 1024) return `${value} B`
  return `${Math.round(value / 1024)} KB`
}

export function CuraRecoveryModal({ agent, onClose, onQueued }: {
  agent: WorkstationAgent
  onClose: () => void
  onQueued: (message: string) => void
}) {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState('')
  const [step, setStep] = useState<'select' | 'review'>('select')
  const snapshots = useQuery({
    queryKey: ['cura-recovery-snapshots', agent.id],
    queryFn: () => apiFetch<CuraRecoverySnapshot[]>(`/workstation-agents/${agent.id}/cura-recovery-snapshots`),
  })
  const selected = snapshots.data?.find((snapshot) => snapshot.id === selectedId) ?? null
  const restore = useMutation({
    mutationFn: (snapshot: CuraRecoverySnapshot) => apiFetch<CuraRecoveryRestore>(`/workstation-agents/${agent.id}/cura-recovery-restores`, {
      method: 'POST',
      body: JSON.stringify({ snapshot_id: snapshot.id, confirmed: true }),
    }),
    onSuccess: async (_, snapshot) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workstation-agents'] }),
        queryClient.invalidateQueries({ queryKey: ['cura-recovery-snapshots', agent.id] }),
        queryClient.invalidateQueries({ queryKey: ['diagnostics'] }),
      ])
      onQueued(`Cura ${snapshot.cura_version} recovery was queued for ${agent.display_name}. Close Cura and leave it closed until the workstation reports that recovery is ready.`)
      onClose()
    },
  })

  const footer = step === 'select'
    ? <>
      <button className="button" type="button" onClick={onClose}>Cancel</button>
      <button className="button button--primary" type="button" disabled={!selected} onClick={() => setStep('review')}>Review recovery</button>
    </>
    : <>
      <button className="button" type="button" onClick={() => setStep('select')}>Back to recovery points</button>
      <button className="button button--primary" type="button" disabled={!selected || restore.isPending} onClick={() => selected && restore.mutate(selected)}>
        <RotateCcw size={16} />{restore.isPending ? 'Queuing…' : 'Restore Cura setup'}
      </button>
    </>

  return <Modal
    title={step === 'select' ? `Recovery points for ${agent.display_name}` : 'Review Cura recovery'}
    description={step === 'select'
      ? 'Choose one exact-version snapshot. Filament Manager retains the ten most recent distinct configurations for each Cura installation.'
      : 'Confirm the saved configuration and required recovery sequence before the workstation changes Cura files.'}
    onClose={onClose}
    size="wide"
    footer={footer}
  >
    {step === 'select' ? <EditorSection title="Saved Cura configurations" description="Snapshots are captured automatically only while Cura is closed. Apparent resets are blocked from replacing the last known-good point.">
      {snapshots.isLoading ? <LoadingState /> : snapshots.error ? <p className="form-error" role="alert">{snapshots.error.message}</p> : !snapshots.data?.length ? <EmptyState icon={DatabaseBackup} title="No recovery points yet" description="Close Cura and leave the workstation agent running. An operational configuration with at least one printer will be captured automatically." /> : <div className="cura-recovery-list">{snapshots.data.map((snapshot, index) => <button
        className={`cura-recovery-item${snapshot.id === selectedId ? ' cura-recovery-item--selected' : ''}`}
        type="button"
        aria-pressed={snapshot.id === selectedId}
        onClick={() => setSelectedId(snapshot.id)}
        key={snapshot.id}
      >
        <span><strong>Cura {snapshot.cura_version}{index === 0 ? ' · Latest' : ''}</strong><small>{dateTime(snapshot.captured_at)} · Settings v{snapshot.setting_version ?? 'unknown'}</small></span>
        <span className="cura-recovery-item__counts"><small>{snapshot.machine_count} printer{snapshot.machine_count === 1 ? '' : 's'}</small><small>{snapshot.quality_profile_count} quality file{snapshot.quality_profile_count === 1 ? '' : 's'}</small><small>{snapshot.plugin_count} plugin{snapshot.plugin_count === 1 ? '' : 's'}</small><small>{snapshot.file_count} files · {fileSize(snapshot.total_bytes)}</small></span>
      </button>)}</div>}
    </EditorSection> : selected ? <div className="editor-form">
      <EditorSection title="Recovery point" description="Recovery is limited to the same workstation and exact Cura version.">
        <dl className="definition-list">
          <div><dt>Captured</dt><dd>{dateTime(selected.captured_at)}</dd></div>
          <div><dt>Cura version</dt><dd>{selected.cura_version}</dd></div>
          <div><dt>Printers</dt><dd>{selected.machine_count}</dd></div>
          <div><dt>Quality configuration files</dt><dd>{selected.quality_profile_count}</dd></div>
          <div><dt>Saved configuration</dt><dd>{selected.file_count} files · {fileSize(selected.total_bytes)}</dd></div>
        </dl>
      </EditorSection>
      <EditorSection title="Plugin inventory" description="Cura account synchronization installs plugin code. Filament Manager records names and versions for verification only.">
        {selected.plugins.length ? <ul className="feature-list">{selected.plugins.map((plugin) => <li key={plugin.package_id}><ShieldCheck size={17} /><span><strong>{plugin.display_name}</strong><small>{plugin.version} · {plugin.enabled ? 'Enabled' : 'Disabled when captured'}</small></span></li>)}</ul> : <p className="muted">No account-installed plugins were recorded in this recovery point.</p>}
      </EditorSection>
      <EditorSection title="Recovery sequence" description="Complete these steps in order so Cura and its plugins exist before their safe settings are restored.">
        <ol className="cura-recovery-steps"><li>Install or reset the same Cura version.</li><li>Open Cura, sign in to your Cura account, and wait for its plugins to install.</li><li>Close Cura completely.</li><li>Confirm this recovery and leave Cura closed until the status returns to Ready.</li><li>Re-enter Moonraker, OctoPrint, or other connection credentials if needed.</li></ol>
      </EditorSection>
      <div className="warning-note"><strong>Credentials stay local.</strong> Account sessions, passwords, tokens, API keys, private URLs, local paths, and plugin executable files are never uploaded or restored. The current Cura login and connection secrets remain untouched.</div>
      {restore.error ? <p className="form-error" role="alert">{restore.error.message}</p> : null}
    </div> : null}
  </Modal>
}
