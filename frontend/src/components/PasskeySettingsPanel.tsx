/** Account-owned passkeys, with fresh password confirmation for every mutation. */
import { Fingerprint, Plus, Trash2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { apiFetch } from '../api/client'
import { dateTime } from '../lib/format'
import { passkeyError, registerPasskey, supportsPasskeys, type SavedPasskey } from '../lib/passkeys'
import { Modal } from './Modal'

export function PasskeySettingsPanel() {
  const client = useQueryClient()
  const keys = useQuery({ queryKey: ['passkeys'], queryFn: () => apiFetch<SavedPasskey[]>('/auth/passkeys') })
  const readiness = useQuery({ queryKey: ['passkey-availability'], queryFn: () => apiFetch<{ available: boolean }>('/auth/passkeys/availability') })
  const [action, setAction] = useState<'add' | SavedPasskey | null>(null)
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => { controller.current?.abort() }, [])
  const mutation = useMutation({
    mutationFn: async () => {
      const abort = new AbortController()
      controller.current = abort
      if (action === 'add') return registerPasskey(name.trim(), password, abort.signal)
      if (action) await apiFetch<void>(`/auth/passkeys/${action.id}/remove`, { method: 'POST', signal: abort.signal, body: JSON.stringify({ current_password: password }) })
    },
    onSuccess: async () => {
      setMessage(action === 'add' ? 'Passkey added. You can use it for your next sign-in.' : 'Passkey removed. Other browser sessions were signed out.')
      setAction(null)
      setPassword('')
      try { await client.invalidateQueries({ queryKey: ['passkeys'] }) }
      catch { setMessage('Your change was saved. Refresh the page to update the passkey list.') }
    },
    onError: (caught) => { if (!controller.current?.signal.aborted) setError(passkeyError(caught)) },
  })
  const supported = supportsPasskeys() && readiness.data?.available === true
  function open(next: 'add' | SavedPasskey) {
    setAction(next); setName(''); setPassword(''); setError(''); setMessage(''); mutation.reset()
  }
  function close() {
    controller.current?.abort(); setAction(null); setPassword(''); setError('')
  }
  function submit(event: FormEvent) {
    event.preventDefault(); setError(''); mutation.mutate()
  }
  return <article className="card settings-section settings-section--wide passkey-settings" aria-labelledby="passkey-settings-title">
    <header className="card__header"><div><p className="eyebrow">Secure sign-in</p><h2 id="passkey-settings-title"><Fingerprint size={20} /> Passkeys</h2></div><button className="button button--primary" disabled={!supported || keys.isPending || keys.isError} onClick={() => open('add')}><Plus size={17} /> Add passkey</button></header>
    <p className="muted">Sign in on your phone or computer with a fingerprint, face, device PIN, or security key. Your password remains available.</p>
    {!supported && !readiness.isPending ? <p className="inline-note">Passkey setup requires a supported browser and the configured HTTPS address. You can still remove a saved passkey using your password.</p> : null}
    {keys.isPending ? <p role="status">Loading passkeys…</p> : keys.isError ? <p className="form-error" role="alert">Passkeys could not be loaded. Please retry.</p> : keys.data?.length ? <div className="passkey-list">{keys.data.map((key) => <div className="passkey-row" key={key.id}><span className="passkey-row__icon"><Fingerprint size={22} /></span><div><strong>{key.name}</strong><small>Added {dateTime(key.created_at)}</small><small>{key.last_used_at ? `Last used ${dateTime(key.last_used_at)}` : 'Not used to sign in yet'}</small></div><button className="button" onClick={() => open(key)} aria-label={`Remove passkey ${key.name}`}><Trash2 size={16} /> Remove</button></div>)}</div> : <div className="passkey-empty"><Fingerprint size={28} /><div><strong>No passkeys yet</strong><p>Add a passkey on this device or save one with your password manager.</p></div></div>}
    <p className="field-help">Your browser handles passkey storage and device verification. Filament Manager never receives your fingerprint, face data, or private key.</p>
    {message ? <p className="success-note" role="status">{message}</p> : null}
    {action ? <Modal title={action === 'add' ? 'Add a passkey' : 'Remove passkey'} description={action === 'add' ? 'Confirm your password, then follow your browser’s passkey setup.' : `Remove ${action.name}? This prevents that passkey from signing in and signs out other browser sessions. Your password and other passkeys remain available.`} onClose={close} footer={<><button className="button" onClick={close}>Cancel</button><button form="passkey-management" className={`button ${action === 'add' ? 'button--primary' : 'button--danger'}`} disabled={mutation.isPending}>{mutation.isPending ? 'Waiting for verification…' : action === 'add' ? 'Create passkey' : 'Remove passkey'}</button></>}>
      <form id="passkey-management" className="editor-form" onSubmit={submit}>
        {action === 'add' ? <label>Passkey name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="For example, My phone" maxLength={80} required /></label> : null}
        <label>Current password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" maxLength={256} required /></label>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
      </form>
    </Modal> : null}
  </article>
}
