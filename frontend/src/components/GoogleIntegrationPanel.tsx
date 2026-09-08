import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Cloud, ExternalLink, RefreshCw } from 'lucide-react'
import { actionableApiError, apiFetch } from '../api/client'
import { Modal } from './Modal'
import { GoogleSetupWizard } from './GoogleSetupWizard'

interface GoogleStatus {
  ready: boolean
  legacy: boolean
  connected: boolean
  redirect_uri: string
  spreadsheet_url: string | null
  last_synced_at: string | null
  last_error: string | null
  next_attempt_at?: string | null
  sync_requested: boolean
  interval_seconds: number
}

/** Setup and explicit publication controls; credentials never enter browser state. */
export function GoogleIntegrationPanel() {
  const cache = useQueryClient()
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [setup, setSetup] = useState(false)
  const query = useQuery({ queryKey: ['google-integration'], queryFn: () => apiFetch<GoogleStatus>('/settings/google'), refetchInterval: 10000 })
  const action = useMutation({
    mutationFn: async (operation: 'connect' | 'sync' | 'disconnect') => {
      const result = await apiFetch<{ authorization_url?: string }>(`/settings/google/${operation}`, { method: 'POST' })
      if (operation === 'connect' && result.authorization_url) window.location.assign(result.authorization_url)
    },
    onSuccess: () => {
      setConfirmDisconnect(false)
      void cache.invalidateQueries({ queryKey: ['google-integration'] })
    },
  })
  const data = query.data
  const callback = new URLSearchParams(window.location.search).get('google')
  return <article className="card settings-section settings-section--wide google-integration">
    <header className="card__header"><div><p className="eyebrow">One-way publication</p><h2><Cloud size={20} /> Google integration</h2></div></header>
    <p>Keep a <strong>Filament Manager</strong> spreadsheet in your Google Drive, with linked, filterable inventory, templates, calibration and print history tables.</p>
    <p className="muted">The app is authoritative. Spreadsheet edits never come back to the app and are replaced on publication. Credentials, security logs and binary files are excluded.</p>
    {callback === 'connected' && <p role="status" className="security-note">Google connected. The worker will create and populate your workbook.</p>}
    {callback === 'failed' && <p role="alert" className="form-error">Google sign-in was not completed. Stay signed in to this app, check setup, and connect again.</p>}
    {(query.error || action.error) && <p className="form-error" role="alert">{actionableApiError(action.error ?? query.error)}</p>}
    {query.isLoading && <p role="status">Loading Google setup…</p>}
    {data && <>
      <dl className="plate-facts">
        <div><dt>Connection</dt><dd>{data.connected ? data.legacy ? 'Service account connected' : 'Google connected' : 'Not connected'}</dd></div>
        <div><dt>Last published</dt><dd>{data.last_synced_at ? new Date(data.last_synced_at).toLocaleString() : 'Not published yet'}</dd></div>
      </dl>
      {data.last_error && <p className="form-error" role="alert">{data.last_error}</p>}
      {data.last_error && data.next_attempt_at && <p className="muted">Automatic retry: {new Date(data.next_attempt_at).toLocaleString()}. Use Sync now after correcting the problem.</p>}
      {data.sync_requested && <p role="status">Sync queued. Publishing waits while a print is in progress.</p>}
      <p className="muted">Changes are checked every {data.interval_seconds} seconds. Rapid changes are grouped; publication catches up after printing.</p>
      {!data.ready && !data.legacy && <section aria-label="Google setup instructions">
        <h3>One-time Google Cloud setup</h3>
        <ol>
          <li>Enable the Google Drive API and Google Sheets API in your Google Cloud project.</li>
          <li>Configure consent and create an OAuth client with type <strong>Web application</strong>. Add this exact authorized redirect URI:<br /><code className="google-redirect">{data.redirect_uri}</code></li>
          <li>Choose Guided setup to upload your Google credentials file securely. The app handles encryption and configuration.</li>
        </ol>
        <p>Use HTTPS. For an External consent screen, add your account as a test user; testing grants may expire after seven days. Use Production consent for ongoing synchronization.</p>
        <a className="text-link" href="https://github.com/cosmicc/filament_manager/blob/main/docs/GOOGLE_SHEETS.md" target="_blank" rel="noreferrer">Complete setup guide <ExternalLink size={14} /></a>
      </section>}
      <div className="detail-actions">
        {!data.legacy && <button className="button" onClick={() => setSetup(true)}>Guided setup</button>}
        {!data.legacy && <button className="button button--primary" disabled={!data.ready || action.isPending} onClick={() => action.mutate('connect')}><Cloud size={16} />{data.connected ? 'Reconnect Google' : 'Connect Google'}</button>}
        <button className="button" disabled={!data.connected || action.isPending || (data.sync_requested && !data.last_error)} onClick={() => action.mutate('sync')}><RefreshCw size={16} />Sync now</button>
        {data.spreadsheet_url && <a className="button" href={data.spreadsheet_url} target="_blank" rel="noreferrer"><ExternalLink size={16} />Open spreadsheet</a>}
        {data.connected && !data.legacy && <button className="button" disabled={action.isPending} onClick={() => setConfirmDisconnect(true)}>Disconnect</button>}
      </div>
    </>}
    {setup && data && <GoogleSetupWizard redirectUri={data.redirect_uri} connected={data.connected} onClose={() => setSetup(false)} onSaved={() => { setSetup(false); void cache.invalidateQueries({ queryKey: ['google-integration'] }) }} />}
    {confirmDisconnect && <Modal title="Disconnect Google?" onClose={() => setConfirmDisconnect(false)}>
      <p>Automatic publication stops and saved Google access is removed from this app. Your spreadsheet stays in Drive. You can also remove the app’s grant in your Google Account permissions.</p>
      <div className="detail-actions"><button className="button" onClick={() => setConfirmDisconnect(false)}>Cancel</button><button className="button button--primary" disabled={action.isPending} onClick={() => action.mutate('disconnect')}>Disconnect Google</button></div>
    </Modal>}
  </article>
}
