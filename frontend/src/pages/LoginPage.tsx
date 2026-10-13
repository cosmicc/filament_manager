import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Fingerprint } from 'lucide-react'
import { apiFetch } from '../api/client'
import { passkeyError, recognizedPasskeyBrowser, supportsPasskeyAutofill, supportsPasskeys } from '../lib/passkeys'
import { ApiClientError } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { APP_VERSION } from '../lib/version'

export default function LoginPage() {
  const { login, loginWithPasskey } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [passkeysAvailable, setPasskeysAvailable] = useState(false)
  const [passkeyBusy, setPasskeyBusy] = useState(false)
  const manualStarting = useRef(false)
  const ceremony = useRef<{ controller: AbortController; promise: Promise<void> } | null>(null)

  async function cancelPasskey() {
    const current = ceremony.current
    if (!current) return
    current.controller.abort()
    await current.promise
    if (ceremony.current === current) ceremony.current = null
  }

  async function manualPasskey() {
    if (manualStarting.current) return
    manualStarting.current = true
    try {
      await cancelPasskey()
      setError('')
      setPasskeyBusy(true)
      const controller = new AbortController()
      const promise = loginWithPasskey(controller.signal)
        .catch((caught: unknown) => { if (!controller.signal.aborted) setError(passkeyError(caught)) })
        .finally(() => { if (!controller.signal.aborted) setPasskeyBusy(false) })
      ceremony.current = { controller, promise }
      await promise
    } finally { manualStarting.current = false }
  }

  useEffect(() => {
    const controller = new AbortController()
    const promise = (async () => {
      if (!supportsPasskeys()) return
      const readiness = await apiFetch<{ available: boolean }>('/auth/passkeys/availability', { signal: controller.signal })
      if (controller.signal.aborted || !readiness.available) return
      setPasskeysAvailable(true)
      const recognized = recognizedPasskeyBrowser()
      const conditional = !recognized && await supportsPasskeyAutofill()
      if (controller.signal.aborted || (!recognized && !conditional)) return
      if (recognized) setPasskeyBusy(true)
      try { await loginWithPasskey(controller.signal, conditional) }
      finally { if (!controller.signal.aborted) setPasskeyBusy(false) }
    })().catch(() => { /* Automatic cancellation/failure leaves password and manual sign-in available. */ })
    ceremony.current = { controller, promise }
    return () => { controller.abort(); ceremony.current?.controller.abort() }
  }, [loginWithPasskey])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    await cancelPasskey()
    setPasskeyBusy(false)
    setError('')
    try {
      await login(username, password)
    } catch (caught) {
      setError(caught instanceof ApiClientError ? caught.message : 'Sign-in failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-brand">
          <img src="/assets/filament-manager-icon-128.png" alt="" />
          <div><strong>Filament</strong><span>Manager</span></div>
        </div>
        <div className="login-card__intro">
          <p className="login-card__eyebrow">PRINT OPERATIONS</p>
          <h1>The ultimate 3D printing filament and Cura manager</h1>
          <p>Coordinate filament inventory, material profiles, calibration, Cura synchronization, and live printer operations from one purpose-built workspace.</p>
        </div>
        <div className="login-passkey">
          <button type="button" className="button button--full login-passkey__button" disabled={!passkeysAvailable || submitting} onClick={() => void manualPasskey()}>
            <Fingerprint size={22} /> {passkeyBusy ? 'Use your passkey…' : 'Sign in with passkey'}
          </button>
          <p className="field-help" role="status">{passkeysAvailable ? 'Use your fingerprint, face, device PIN, or security key.' : 'Passkeys require a supported browser and the configured HTTPS address.'}</p>
        </div>
        <div className="login-divider"><span>or use your password</span></div>
        <form onSubmit={(event) => void submit(event)}>
          <label>Username<input autoComplete="username webauthn" required minLength={2} value={username} onChange={(event) => setUsername(event.target.value)} autoFocus /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button--primary button--full" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <p className="login-card__version">Filament Manager v{APP_VERSION}</p>
      </section>
      <aside className="login-art" aria-hidden="true">
        <img src="/assets/login-delta-workshop.webp" alt="" />
        <div className="login-art__label"><span>Filament Manager</span><strong>Inventory · Cura · Printer</strong></div>
      </aside>
    </main>
  )
}
