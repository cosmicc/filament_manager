import { KeyRound, LogOut, ShieldCheck } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function PasswordChangePage() {
  const { changePassword, logout, user } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (newPassword !== confirmation) {
      setError('The new passwords do not match.')
      return
    }
    setPending(true)
    setError('')
    try {
      await changePassword(currentPassword, newPassword)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The password could not be changed')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="password-change-page">
      <section className="auth-card password-change-card">
        <div className="auth-card__mark"><KeyRound size={28} /></div>
        <p className="eyebrow">Secure account setup</p>
        <h1>Choose your own password</h1>
        <p>Hello {user?.display_name}. Your temporary password must be replaced before the workshop can be opened.</p>
        <form className="form-stack" onSubmit={submit}>
          <label>Temporary password<input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" required autoFocus /></label>
          <label>New password<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={10} maxLength={256} autoComplete="new-password" required /></label>
          <label>Confirm new password<input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={10} maxLength={256} autoComplete="new-password" required /></label>
          <p className="security-note"><ShieldCheck size={16} /> Other sessions will be revoked when the password changes.</p>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button button--primary" disabled={pending}>{pending ? 'Changing…' : 'Change password'}</button>
          <button className="button" type="button" onClick={() => void logout()}><LogOut size={17} /> Sign out</button>
        </form>
      </section>
    </main>
  )
}
