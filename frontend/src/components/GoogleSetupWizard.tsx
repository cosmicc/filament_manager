import { useState } from 'react'
import { apiFetch, actionableApiError } from '../api/client'
import { EditorSection } from './EditorSection'
import { Modal } from './Modal'

/** Guide Google's unavoidable console steps without retaining client secrets in UI storage. */
export function GoogleSetupWizard({ redirectUri, connected, onClose, onSaved }: {
  redirectUri: string
  connected: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [step, setStep] = useState(0)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const titles = ['Google project', 'Enable APIs', 'Consent and client', 'Upload credentials']
  return <Modal title="Set up Google Sheets" onClose={onClose} size="wide" footer={<>
    <button className="button" type="button" disabled={pending} onClick={onClose}>Cancel</button>
    {step > 0 && <button className="button" type="button" disabled={pending} onClick={() => setStep(step - 1)}>Back</button>}
    {step < 3 ? <button className="button button--primary" type="button" onClick={() => setStep(step + 1)}>Next</button>
      : <button className="button button--primary" form="google-setup" disabled={pending}>{pending ? 'Saving securely…' : 'Save credentials'}</button>}
  </>}>
    <p className="eyebrow">Step {step + 1} of 4 · {titles[step]}</p>
    <p>Google requires a one-time project and consent setup. This guide keeps the app configuration here—no client-secret environment variables or redeployment needed.</p>
    {step === 0 && <EditorSection title="Create or select a Google project">
      <p>Sign in with the account that will own your spreadsheet. Create a project named Filament Manager, or select your existing project.</p>
      <a className="button" href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noreferrer">Open Google Cloud</a>
      <p className="muted">Keep the same project selected throughout these steps. Return here and choose Next when ready.</p>
    </EditorSection>}
    {step === 1 && <EditorSection title="Enable both Google APIs">
      <p>Open each page, verify your project, and choose Enable. If Manage is shown, that API is already enabled.</p>
      <div className="detail-actions">
        <a className="button" href="https://console.cloud.google.com/apis/library/drive.googleapis.com" target="_blank" rel="noreferrer">Enable Drive API</a>
        <a className="button" href="https://console.cloud.google.com/apis/library/sheets.googleapis.com" target="_blank" rel="noreferrer">Enable Sheets API</a>
      </div>
    </EditorSection>}
    {step === 2 && <EditorSection title="Configure consent and create a Web client">
      <ol>
        <li>Open Google Auth Platform. Complete branding/contact details and choose the audience appropriate for your account.</li>
        <li>For External / Testing, add yourself as a test user. Testing grants normally expire after seven days; use In production for ongoing synchronization, subject to Google's checks.</li>
        <li>Under Data access, add <code className="google-redirect">https://www.googleapis.com/auth/drive.file</code>. The app only requests access to files it creates or you explicitly authorize.</li>
        <li>Under Clients, create an OAuth client of type <strong>Web application</strong>. Add this exact Authorized redirect URI:</li>
      </ol>
      <code className="google-redirect">{redirectUri}</code>
      <div className="detail-actions">
        <button className="button" type="button" onClick={async () => { try { await navigator.clipboard.writeText(redirectUri); setCopied(true) } catch { setError('Copy the displayed redirect URL manually.') } }}>{copied ? 'Copied' : 'Copy redirect URL'}</button>
        <a className="button" href="https://console.cloud.google.com/auth/overview" target="_blank" rel="noreferrer">Open Google Auth Platform</a>
      </div>
      <p>Download the client's JSON credentials file. Upload it in the next step, not into chat or a public repository.</p>
    </EditorSection>}
    {step === 3 && <form id="google-setup" className="editor-form" onSubmit={async (event) => {
      event.preventDefault()
      const form = event.currentTarget
      const file = (form.elements.namedItem('credentials') as HTMLInputElement).files?.[0]
      if (!file || file.size > 32768) { setError('Choose a Google Web OAuth credentials JSON file under 32 KB.'); return }
      setPending(true); setError('')
      try {
        await apiFetch('/settings/google/setup', { method: 'POST', body: JSON.stringify({ credentials_json: await file.text() }) })
        form.reset()
        onSaved()
      } catch (reason) { setError(actionableApiError(reason)) }
      finally { setPending(false) }
    }}>
      <EditorSection title="Save securely in Filament Manager">
        <label>Google credentials JSON<input name="credentials" type="file" accept=".json,application/json" required disabled={pending} /></label>
        <p>The server validates the client and redirect URL, encrypts the secret, and keeps its encryption key separately in the private shared application data volume. Back up that volume as well as the database.</p>
        {connected && <label className="checkbox-label"><input type="checkbox" required />I understand that replacing credentials disconnects Google until I connect again. The spreadsheet is retained.</label>}
        <p>After saving, choose Connect Google. Your first successful publication verifies access and creates the Filament Manager spreadsheet.</p>
      </EditorSection>
    </form>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </Modal>
}
