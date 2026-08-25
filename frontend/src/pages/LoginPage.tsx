import { type FormEvent, useState } from 'react'
import { ApiClientError } from '../api/client'
import { useAuth } from '../context/AuthContext'

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
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
        <form onSubmit={(event) => void submit(event)}>
          <label>Username<input autoComplete="username" required minLength={2} value={username} onChange={(event) => setUsername(event.target.value)} autoFocus /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button--primary button--full" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </section>
      <aside className="login-art" aria-hidden="true">
        <img src="/assets/login-delta-workshop.webp" alt="" />
        <div className="login-art__label"><span>Filament Manager</span><strong>Inventory · Cura · Printer</strong></div>
      </aside>
    </main>
  )
}
