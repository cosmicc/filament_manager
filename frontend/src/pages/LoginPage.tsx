import { LockKeyhole } from 'lucide-react'
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
          <img src="/assets/filament-manager-mark.png" alt="" />
          <div><strong>Filament</strong><span>Manager</span></div>
        </div>
        <div className="login-card__intro">
          <span className="login-lock"><LockKeyhole size={21} /></span>
          <h1>Welcome back</h1>
          <p>Sign in with your local workshop account.</p>
        </div>
        <form onSubmit={(event) => void submit(event)}>
          <label>Username<input autoComplete="username" required minLength={2} value={username} onChange={(event) => setUsername(event.target.value)} autoFocus /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button--primary button--full" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <p className="login-card__security">Session credentials stay on this server. Filament Manager never exposes integration secrets to the browser.</p>
      </section>
      <aside className="login-art" aria-hidden="true">
        <div className="login-art__rings"><span /><span /><span /></div>
        <div className="login-art__copy"><p>Workshop inventory, calibration, and printer state.</p><strong>One trustworthy place.</strong></div>
      </aside>
    </main>
  )
}
