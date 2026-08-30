import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseBackup, Download, FileUp, RotateCcw, Save, ShieldAlert } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import type { DatabaseBackupArchive, DatabaseBackupOverview, DatabaseRestorePreparation } from '../api/types'
import { dateTime, titleCase } from '../lib/format'
import { EditorSection } from './EditorSection'
import { EmptyState } from './EmptyState'
import { LoadingState } from './LoadingState'
import { Modal } from './Modal'
import { StatusPill } from './StatusPill'

function fileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function DatabaseBackupPanel({ isAdministrator }: { isAdministrator: boolean }) {
  const client = useQueryClient()
  const [enabled, setEnabled] = useState(true)
  const [intervalHours, setIntervalHours] = useState(24)
  const [retentionCount, setRetentionCount] = useState(10)
  const [selected, setSelected] = useState<DatabaseBackupArchive | null>(null)
  const [confirmation, setConfirmation] = useState('')
  const [notice, setNotice] = useState('')
  const overview = useQuery({
    queryKey: ['database-backups'],
    queryFn: () => apiFetch<DatabaseBackupOverview>('/diagnostics/database-backups'),
    refetchInterval: 30_000,
  })

  useEffect(() => {
    if (!overview.data) return
    setEnabled(overview.data.policy.enabled)
    setIntervalHours(overview.data.policy.interval_hours)
    setRetentionCount(overview.data.policy.retention_count)
  }, [overview.data])

  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['database-backups'] }),
      client.invalidateQueries({ queryKey: ['diagnostics'] }),
    ])
  }
  const savePolicy = useMutation({
    mutationFn: () => apiFetch('/diagnostics/database-backups/policy', {
      method: 'PUT',
      body: JSON.stringify({
        enabled,
        interval_hours: intervalHours,
        retention_count: retentionCount,
        expected_version: overview.data?.policy.record_version ?? 0,
      }),
    }),
    onSuccess: async () => { setNotice('Automatic database backup settings saved.'); await refresh() },
  })
  const createBackup = useMutation({
    mutationFn: () => apiFetch<DatabaseBackupArchive>('/diagnostics/database-backups', { method: 'POST' }),
    onSuccess: async () => { setNotice('A new downloadable database backup was created.'); await refresh() },
  })
  const importBackup = useMutation({
    mutationFn: (file: File) => apiFetch<DatabaseBackupArchive>('/diagnostics/database-backups/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/zip' },
      body: file,
    }),
    onSuccess: async (archive) => {
      await refresh()
      setConfirmation('')
      setSelected(archive)
    },
  })
  const prepareRestore = useMutation({
    mutationFn: (archive: DatabaseBackupArchive) => apiFetch<DatabaseRestorePreparation>(`/diagnostics/database-backups/${archive.id}/restore-request`, {
      method: 'POST',
      body: JSON.stringify({ confirmation }),
    }),
    onSuccess: async () => {
      setSelected(null)
      setConfirmation('')
      setNotice('Restore prepared. Stop the web and worker services before starting the dedicated database-restore service.')
      await refresh()
    },
  })
  const cancelRestore = useMutation({
    mutationFn: () => apiFetch<void>('/diagnostics/database-backups/restore-request', { method: 'DELETE' }),
    onSuccess: async () => { setNotice('The pending database restore was cancelled.'); await refresh() },
  })
  const error = overview.error ?? savePolicy.error ?? createBackup.error ?? importBackup.error ?? prepareRestore.error ?? cancelRestore.error
  const submitPolicy = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    savePolicy.mutate()
  }

  return <section className="card diagnostic-actions">
    <div className="section-heading">
      <div>
        <p className="eyebrow">Catastrophic recovery</p>
        <h2><DatabaseBackup size={20} /> Database backups</h2>
        <p>Compressed snapshots contain the complete canonical Filament Manager PostgreSQL database. Spoolman remains independently backed up.</p>
      </div>
      {isAdministrator ? <div className="detail-actions">
        <button className="button button--primary" disabled={createBackup.isPending} onClick={() => createBackup.mutate()}><DatabaseBackup size={16} /> {createBackup.isPending ? 'Backing up…' : 'Back up now'}</button>
        <label className="button file-button"><FileUp size={16} /> {importBackup.isPending ? 'Importing…' : 'Import backup'}<input type="file" accept="application/zip,.zip" disabled={importBackup.isPending} onChange={(event) => { const file = event.target.files?.[0]; if (file) importBackup.mutate(file); event.currentTarget.value = '' }} /></label>
      </div> : null}
    </div>

    {overview.isLoading ? <LoadingState label="Loading database backups" /> : overview.data ? <>
      <div className="diagnostic-check-grid">
        <article className="diagnostic-check"><div><strong>Automatic backups</strong><p>{overview.data.policy.enabled ? `Every ${overview.data.policy.interval_hours} hour${overview.data.policy.interval_hours === 1 ? '' : 's'}; keep the newest ${overview.data.policy.retention_count}. Backups wait until no print is active.` : 'Scheduled backups are disabled.'}</p><small>{overview.data.status.last_success_at ? `Last successful backup ${dateTime(overview.data.status.last_success_at)}.` : 'No successful backup has been recorded.'}{overview.data.status.next_retry_at ? ` Next automatic retry ${dateTime(overview.data.status.next_retry_at)}.` : ''}</small></div><StatusPill status={overview.data.status.status === 'healthy' ? 'healthy' : overview.data.status.status === 'never' ? 'warning' : overview.data.status.status} /></article>
        <article className="diagnostic-check"><div><strong>Offline restore</strong><p>{overview.data.pending_restore ? 'A restore is prepared and waiting for controlled maintenance.' : 'No database restore is pending.'}</p><small>Restore automatically creates a pre-restore safety backup and revokes all browser sessions.</small></div><StatusPill status={overview.data.pending_restore ? 'warning' : 'healthy'} /></article>
      </div>
      {isAdministrator ? <form className="form-grid" onSubmit={submitPolicy}>
        <label className="checkbox-row"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Enable scheduled backups</label>
        <label>Interval (hours)<input type="number" min="1" max={24 * 30} value={intervalHours} onChange={(event) => setIntervalHours(Number(event.target.value))} required /></label>
        <label>Automatic backups retained<input type="number" min="1" max="100" value={retentionCount} onChange={(event) => setRetentionCount(Number(event.target.value))} required /></label>
        <div className="detail-actions"><button className="button" disabled={savePolicy.isPending}><Save size={16} /> {savePolicy.isPending ? 'Saving…' : 'Save schedule'}</button></div>
      </form> : null}
      {overview.data.pending_restore ? <div className="warning-note"><strong>Maintenance restore is pending.</strong> Stop both application services, run the zero-replica <code>database-restore</code> service once, verify it completed, then restart web and worker. The application must not be serving requests during restoration.{isAdministrator ? <div className="detail-actions"><button className="button" disabled={cancelRestore.isPending} onClick={() => cancelRestore.mutate()}>Cancel pending restore</button></div> : null}</div> : null}
      <div className="section-heading"><div><p className="eyebrow">Validated ZIP archives</p><h3>Available backups</h3><p>Downloaded archives can be imported into this or another Filament Manager installation. Import only files from a trusted Filament Manager instance.</p></div></div>
      {overview.data.archives.length ? <div className="mobile-card-list mobile-card-list--always">{overview.data.archives.map((archive) => <article className="mobile-data-card" key={`${archive.storage_kind}-${archive.id}`}><div><strong>{dateTime(archive.created_at)}</strong><StatusPill status={archive.storage_kind === 'imported' ? 'warning' : 'healthy'} label={titleCase(archive.storage_kind)} /></div><span>Filament Manager v{archive.application_version} · {fileSize(archive.size_bytes)} · {titleCase(archive.trigger.replaceAll('_', ' '))}</span><small>Database revision {archive.database_revision}</small><div className="detail-actions"><a className="button" href={`/api/v1/diagnostics/database-backups/${archive.id}/download`}><Download size={16} /> Download</a>{isAdministrator ? <button className="button" disabled={Boolean(overview.data.pending_restore)} onClick={() => { setConfirmation(''); setSelected(archive) }}><RotateCcw size={16} /> Restore</button> : null}</div></article>)}</div> : <EmptyState icon={DatabaseBackup} title="No database backups yet" description="The worker creates the first automatic backup when its schedule is due, or an Administrator can create one now." />}
    </> : null}
    {notice ? <p className="deployment-note" role="status">{notice}</p> : null}
    {error ? <p className="form-error" role="alert">{error.message}</p> : null}
    {selected ? <Modal title="Prepare database restore" description="This replaces the complete canonical Filament Manager database during controlled offline maintenance." onClose={() => { setSelected(null); setConfirmation('') }} footer={<><button className="button" onClick={() => { setSelected(null); setConfirmation('') }}>Cancel</button><button className="button button--primary" disabled={confirmation !== 'RESTORE' || prepareRestore.isPending} onClick={() => prepareRestore.mutate(selected)}><ShieldAlert size={16} /> {prepareRestore.isPending ? 'Preparing…' : 'Prepare offline restore'}</button></>}>
      <EditorSection title="Selected backup" description="A new pre-restore safety backup will be created before this archive is applied."><div className="readonly-results"><strong>{dateTime(selected.created_at)}</strong><span>Filament Manager v{selected.application_version} · {fileSize(selected.size_bytes)}</span><span>Database revision {selected.database_revision}</span></div></EditorSection>
      <EditorSection title="Destructive confirmation" description="Web and worker must be stopped before the dedicated restore service runs."><label>Type RESTORE exactly<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoFocus autoComplete="off" /></label></EditorSection>
      {prepareRestore.error ? <p className="form-error" role="alert">{prepareRestore.error.message}</p> : null}
    </Modal> : null}
  </section>
}
