import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseBackup, Pencil, Plus, RotateCcw, ShieldCheck, Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'
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
  const [step, setStep] = useState<'select' | 'review' | 'create' | 'edit' | 'delete'>('select')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
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
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['workstation-agents'] }),
      queryClient.invalidateQueries({ queryKey: ['cura-recovery-snapshots', agent.id] }),
      queryClient.invalidateQueries({ queryKey: ['diagnostics'] }),
    ])
  }
  const capture = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form)
      return apiFetch(`/workstation-agents/${agent.id}/cura-recovery-captures`, {
        method: 'POST',
        body: JSON.stringify({
          installation_id: String(data.get('installation_id')),
          name: name.trim(),
          description: description.trim() || null,
        }),
      })
    },
    onSuccess: async () => {
      await refresh()
      onQueued(`A named Cura backup was queued for ${agent.display_name}. Close Cura so the workstation agent can capture it.`)
      onClose()
    },
  })
  const update = useMutation({
    mutationFn: (snapshot: CuraRecoverySnapshot) => apiFetch<CuraRecoverySnapshot>(`/workstation-agents/${agent.id}/cura-recovery-snapshots/${snapshot.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ expected_version: snapshot.record_version, name: name.trim() || null, description: description.trim() || null }),
    }),
    onSuccess: async () => { await refresh(); setStep('select') },
  })
  const remove = useMutation({
    mutationFn: (snapshot: CuraRecoverySnapshot) => apiFetch<void>(`/workstation-agents/${agent.id}/cura-recovery-snapshots/${snapshot.id}`, {
      method: 'DELETE',
      body: JSON.stringify({ expected_version: snapshot.record_version, confirmed: true }),
    }),
    onSuccess: async () => { setSelectedId(''); await refresh(); setStep('select') },
  })

  const editSnapshot = (snapshot: CuraRecoverySnapshot) => {
    setSelectedId(snapshot.id)
    setName(snapshot.name ?? '')
    setDescription(snapshot.description ?? '')
    setStep('edit')
  }

  const footer = step === 'select'
    ? <>
      <button className="button" type="button" onClick={onClose}>Cancel</button>
      <button className="button" type="button" onClick={() => { setName(''); setDescription(''); setStep('create') }}><Plus size={16} /> New backup</button>
      <button className="button button--primary" type="button" disabled={!selected} onClick={() => setStep('review')}>Review recovery</button>
    </>
    : step === 'review' ? <>
      <button className="button" type="button" onClick={() => setStep('select')}>Back to recovery points</button>
      <button className="button button--primary" type="button" disabled={!selected || restore.isPending} onClick={() => selected && restore.mutate(selected)}>
        <RotateCcw size={16} />{restore.isPending ? 'Queuing…' : 'Restore Cura setup'}
      </button>
    </> : step === 'create' ? <><button className="button" type="button" onClick={() => setStep('select')}>Cancel</button><button className="button button--primary" form="create-cura-backup" disabled={!name.trim() || capture.isPending}><DatabaseBackup size={16} />{capture.isPending ? 'Queuing…' : 'Create backup'}</button></>
      : step === 'edit' ? <><button className="button" type="button" onClick={() => setStep('select')}>Cancel</button><button className="button button--primary" type="button" disabled={!selected || update.isPending} onClick={() => selected && update.mutate(selected)}><Pencil size={16} />{update.isPending ? 'Saving…' : 'Save details'}</button></>
        : <><button className="button" type="button" onClick={() => setStep('select')}>Cancel</button><button className="button button--danger" type="button" disabled={!selected || remove.isPending} onClick={() => selected && remove.mutate(selected)}><Trash2 size={16} />{remove.isPending ? 'Deleting…' : 'Delete backup'}</button></>

  return <Modal
    title={step === 'select' ? `Recovery points for ${agent.display_name}` : step === 'review' ? 'Review Cura recovery' : step === 'create' ? 'Create full Cura backup' : step === 'edit' ? 'Edit backup details' : 'Delete Cura backup'}
    description={step === 'select'
      ? 'Choose one exact-version snapshot. Filament Manager retains the ten most recent distinct configurations for each Cura installation.'
      : step === 'review' ? 'Confirm the saved configuration and required recovery sequence before the workstation changes Cura files.' : step === 'create' ? 'Name a full settings snapshot so it is easy to identify later. Cura must be closed before capture.' : step === 'edit' ? 'Change only the identifying name and description; the captured settings remain immutable.' : 'This permanently removes only the selected recovery point.'}
    onClose={onClose}
    size="wide"
    footer={footer}
  >
    {step === 'select' ? <EditorSection title="Saved Cura configurations" description="Snapshots are captured automatically only while Cura is closed. Apparent resets are blocked from replacing the last known-good point.">
      {snapshots.isLoading ? <LoadingState /> : snapshots.error ? <p className="form-error" role="alert">{snapshots.error.message}</p> : !snapshots.data?.length ? <EmptyState icon={DatabaseBackup} title="No recovery points yet" description="Close Cura and leave the workstation agent running. An operational configuration with at least one printer will be captured automatically." /> : <div className="cura-recovery-list">{snapshots.data.map((snapshot, index) => <div className="cura-recovery-row" key={snapshot.id}><button
        className={`cura-recovery-item${snapshot.id === selectedId ? ' cura-recovery-item--selected' : ''}`}
        type="button"
        aria-pressed={snapshot.id === selectedId}
        onClick={() => setSelectedId(snapshot.id)}
      >
        <span><strong>{snapshot.name ?? `${snapshot.capture_kind === 'manual' ? 'Manual' : 'Automatic'} backup`}</strong><small>Cura {snapshot.cura_version}{index === 0 ? ' · Latest' : ''} · {dateTime(snapshot.captured_at)}</small>{snapshot.description ? <small>{snapshot.description}</small> : null}</span>
        <span className="cura-recovery-item__counts"><small>{snapshot.machine_count} printer{snapshot.machine_count === 1 ? '' : 's'}</small><small>{snapshot.quality_profile_count} quality file{snapshot.quality_profile_count === 1 ? '' : 's'}</small><small>{snapshot.plugin_count} plugin{snapshot.plugin_count === 1 ? '' : 's'}</small><small>{snapshot.file_count} files · {fileSize(snapshot.total_bytes)}</small></span>
      </button><span className="cura-recovery-row__actions"><button className="button button--small" type="button" aria-label={`Edit ${snapshot.name ?? 'backup'}`} onClick={() => editSnapshot(snapshot)}><Pencil size={15} /></button><button className="button button--small button--danger" type="button" aria-label={`Delete ${snapshot.name ?? 'backup'}`} onClick={() => { setSelectedId(snapshot.id); setStep('delete') }}><Trash2 size={15} /></button></span></div>)}</div>}
    </EditorSection> : step === 'review' && selected ? <div className="editor-form">
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
    </div> : step === 'create' ? <form id="create-cura-backup" className="editor-form" onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); capture.mutate(event.currentTarget) }}><EditorSection title="Backup identity" description="The name and description are stored with the sanitized full Cura configuration."><div className="form-grid"><label>Cura installation<select name="installation_id" required autoFocus>{agent.cura_installations.map((installation) => <option key={installation.installation_id} value={installation.installation_id}>Cura {installation.version} · {installation.channel}</option>)}</select></label><label>Backup name<input value={name} onChange={(event) => setName(event.target.value)} minLength={1} maxLength={120} required /></label><label className="form-grid__wide">Description <span className="label-optional">Optional</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} rows={3} /></label></div></EditorSection>{capture.error ? <p className="form-error" role="alert">{capture.error.message}</p> : null}</form> : step === 'edit' ? <div className="editor-form"><EditorSection title="Backup identity" description="Use a concise name and optional note to distinguish this recovery point."><div className="form-grid"><label>Backup name<input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} autoFocus /></label><label className="form-grid__wide">Description <span className="label-optional">Optional</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} rows={3} /></label></div></EditorSection>{update.error ? <p className="form-error" role="alert">{update.error.message}</p> : null}</div> : selected ? <div className="warning-note"><strong>Delete {selected.name ?? 'this backup'}?</strong> This cannot be undone. Other recovery points and the current Cura installation will not be changed.{remove.error ? <p className="form-error" role="alert">{remove.error.message}</p> : null}</div> : null}
  </Modal>
}
