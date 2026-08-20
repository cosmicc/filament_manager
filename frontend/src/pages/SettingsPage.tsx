import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  FileSpreadsheet,
  KeyRound,
  Moon,
  Pencil,
  ShieldCheck,
  Smartphone,
  SlidersHorizontal,
  Sun,
  Upload,
  UserRound,
} from 'lucide-react'
import { type ChangeEvent, type FormEvent, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import type {
  Device,
  OperationalSettings,
  User,
  WorkbookImportCounts,
  WorkbookImportRun,
} from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { THEME_OPTIONS, useTheme } from '../context/ThemeContext'
import { dateTime, titleCase } from '../lib/format'

function AccountEditorModal({ account, onClose }: { account: User; onClose: () => void }) {
  const client = useQueryClient()
  const { changePassword, refreshUser } = useAuth()
  const [username, setUsername] = useState(account.username)
  const [displayName, setDisplayName] = useState(account.display_name)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const refresh = async () => { await client.invalidateQueries({ queryKey: ['users'] }) }
  const update = useMutation({
    mutationFn: () => apiFetch<User>(`/auth/users/${account.id}`, { method: 'PATCH', body: JSON.stringify({ expected_version: account.record_version, username, display_name: displayName }) }),
    onSuccess: async () => { await Promise.all([refresh(), refreshUser()]); onClose() },
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Account could not be updated'),
  })
  const password = useMutation({
    mutationFn: () => changePassword(currentPassword, newPassword),
    onSuccess: () => { setCurrentPassword(''); setNewPassword(''); onClose() },
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Password could not be changed'),
  })
  return <Modal title="Edit account" description="Update the only local administrator identity or replace its password." onClose={onClose} footer={<><button className="button" onClick={onClose}>Cancel</button><button className="button button--primary" onClick={() => update.mutate()} disabled={update.isPending}>Save identity</button></>}>
    <div className="form-stack">
      <EditorSection title="Identity" description="The username is used at sign-in; the display name appears in activity records."><div className="form-grid"><label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} minLength={2} maxLength={80} /></label><label>Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={120} /></label></div></EditorSection>
      <EditorSection title="Change password" description="Changing the password revokes every other browser session."><div className="form-grid"><label>Current password<input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" /></label><label>New password<input type="password" minLength={10} maxLength={256} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" /></label></div><button className="button" disabled={!currentPassword || newPassword.length < 10 || password.isPending} onClick={() => password.mutate()}><KeyRound size={17} /> Change password</button></EditorSection>
      {account.must_change_password ? <p className="warning-note"><KeyRound size={17} /> Password replacement is required at next sign-in.</p> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </div>
  </Modal>
}

function OperationalPolicyPanel({ administrator }: { administrator: boolean }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['operational-settings'], queryFn: () => apiFetch<OperationalSettings>('/settings/operational') })
  const mutation = useMutation({
    mutationFn: (policy: 'warn' | 'block') => {
      if (!query.data) throw new Error('Settings are still loading')
      return apiFetch<OperationalSettings>('/settings/operational', { method: 'PATCH', body: JSON.stringify({ expected_version: query.data.record_version, gcode_inspection_policy: policy }) })
    },
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['operational-settings'] }) },
  })
  return <article className="card settings-section settings-section--wide"><header className="card__header"><div><p className="eyebrow">Print safety</p><h2><SlidersHorizontal size={20} /> G-code inspection policy</h2></div></header><p>Every new print is inspected against its exact managed material profile before filament loading begins.</p>{query.data ? <div className="segmented-control" role="group" aria-label="G-code inspection policy"><button className={query.data.gcode_inspection_policy === 'warn' ? 'active' : ''} disabled={!administrator || mutation.isPending} onClick={() => mutation.mutate('warn')}>Warn and continue</button><button className={query.data.gcode_inspection_policy === 'block' ? 'active' : ''} disabled={!administrator || mutation.isPending} onClick={() => mutation.mutate('block')}>Block mismatches</button></div> : <LoadingState />}{query.data?.gcode_inspection_policy === 'block' ? <p className="warning-note"><AlertTriangle size={17} /> Missing profiles, unavailable inspection data, and detected mismatches pause the print in Fluidd.</p> : <p className="security-note"><ShieldCheck size={17} /> Mismatches remain visible and auditable while the print continues.</p>}{mutation.error ? <p className="form-error">{mutation.error.message}</p> : null}</article>
}

function AppearancePanel() {
  const { theme, setTheme } = useTheme()
  return <article className="card settings-section settings-section--wide"><header className="card__header"><div><p className="eyebrow">Appearance</p><h2>{theme.startsWith('light-') ? <Sun size={20} /> : <Moon size={20} />} Color profile</h2></div></header><p>Choose one of three light or five dark palettes for this browser.</p><div className="theme-profile-grid">{THEME_OPTIONS.map((option) => <button key={option.id} className={`theme-profile${theme === option.id ? ' theme-profile--active' : ''}`} aria-pressed={theme === option.id} onClick={() => setTheme(option.id)}><span className="theme-profile__swatches">{option.swatches.map((color) => <i key={color} style={{ background: color }} />)}</span><span><strong>{option.label}</strong><small>{option.mode === 'light' ? 'Light' : 'Dark'} · {option.description}</small></span></button>)}</div></article>
}

function WorkbookImportPanel({ administrator }: { administrator: boolean }) {
  const client = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [activeRun, setActiveRun] = useState<WorkbookImportRun | null>(null)
  const [error, setError] = useState('')
  const [commitResult, setCommitResult] = useState<WorkbookImportCounts | null>(null)

  const imports = useQuery({
    queryKey: ['workbook-imports'],
    queryFn: () => apiFetch<WorkbookImportRun[]>('/imports/workbook?limit=10'),
    enabled: administrator,
  })
  const displayedRun = activeRun ?? imports.data?.[0] ?? null
  const issueRows = useMemo(
    () => displayedRun?.report.rows.filter((row) => row.errors.length || row.warnings.length) ?? [],
    [displayedRun],
  )

  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Choose an .xlsx workbook')
      const form = new FormData()
      form.append('file', file)
      return apiFetch<WorkbookImportRun>('/imports/workbook/dry-run', { method: 'POST', body: form })
    },
    onSuccess: async (run) => {
      setActiveRun(run)
      setCommitResult(null)
      setError('')
      await client.invalidateQueries({ queryKey: ['workbook-imports'] })
    },
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Workbook validation failed'),
  })

  const commit = useMutation({
    mutationFn: (runId: string) => apiFetch<WorkbookImportCounts>(
      `/imports/workbook/${runId}/commit`,
      { method: 'POST' },
    ),
    onSuccess: async (counts) => {
      setError('')
      setCommitResult(counts)
      setActiveRun((run) => run ? {
        ...run,
        status: 'committed',
        report: {
          ...run.report,
          committed_spools: counts.spools,
          committed_profiles: counts.profiles,
        },
      } : run)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['workbook-imports'] }),
        client.invalidateQueries({ queryKey: ['spools'] }),
        client.invalidateQueries({ queryKey: ['filaments'] }),
        client.invalidateQueries({ queryKey: ['jobs'] }),
        client.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
    },
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Workbook import failed'),
  })

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null)
    setError('')
    setCommitResult(null)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setCommitResult(null)
    upload.mutate()
  }

  const canCommit = Boolean(
    displayedRun?.status === 'validated'
    && displayedRun.stored_workbook
    && displayedRun.report.invalid_rows === 0,
  )

  return (
    <article className="card settings-section settings-section--wide">
      <header className="card__header">
        <div>
          <p className="eyebrow">Initial inventory</p>
          <h2><FileSpreadsheet size={20} /> Workbook import</h2>
        </div>
        {displayedRun && <StatusPill status={displayedRun.status} />}
      </header>

      {!administrator ? (
        <p className="permission-note">
          <ShieldCheck size={18} /> Only administrators can validate and import master workbooks.
        </p>
      ) : (
        <div className="import-panel">
          <form className="import-upload" onSubmit={submit}>
            <label>
              Master workbook
              <input
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={chooseFile}
              />
            </label>
            <button className="button button--primary" type="submit" disabled={!file || upload.isPending}>
              <Upload size={17} /> Validate workbook
            </button>
          </form>

          {displayedRun && (
            <div className="import-result">
              <div className="import-result__heading">
                <div>
                  <strong>{displayedRun.source_name}</strong>
                  <small>Validated {dateTime(displayedRun.completed_at)}</small>
                </div>
                <button
                  className="button"
                  onClick={() => { setError(''); commit.mutate(displayedRun.id) }}
                  disabled={!canCommit || commit.isPending}
                >
                  <CheckCircle2 size={17} /> Commit import
                </button>
              </div>

              <dl className="import-summary">
                <div><dt>Rows</dt><dd>{displayedRun.report.populated_rows}</dd></div>
                <div><dt>Valid</dt><dd>{displayedRun.report.valid_rows}</dd></div>
                <div><dt>Invalid</dt><dd>{displayedRun.report.invalid_rows}</dd></div>
                <div><dt>Columns</dt><dd>{displayedRun.report.inventory_columns}</dd></div>
              </dl>

              {commitResult && (
                <p className="success-note">
                  <CheckCircle2 size={18} />
                  Imported {commitResult.spools} spools, {commitResult.products} products, and{' '}
                  {commitResult.profiles} current profiles.
                </p>
              )}

              {issueRows.length ? (
                <div className="table-card table-card--embedded import-issues">
                  <table>
                    <thead>
                      <tr><th>Row</th><th>Spool</th><th>Status</th><th>Finding</th></tr>
                    </thead>
                    <tbody>
                      {issueRows.slice(0, 25).map((row) => (
                        <tr key={`${row.row_number}-${row.spool_code}`}>
                          <td>{row.row_number}</td>
                          <td><strong>{row.spool_code}</strong></td>
                          <td>
                            <StatusPill
                              status={row.errors.length ? 'error' : 'needs_review'}
                              label={row.errors.length ? 'Error' : 'Warning'}
                            />
                          </td>
                          <td>{[...row.errors, ...row.warnings].join('; ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {issueRows.length > 25 && (
                    <small className="import-issue-count">{issueRows.length - 25} more findings</small>
                  )}
                </div>
              ) : (
                <p className="success-note">
                  <CheckCircle2 size={18} /> Workbook passed validation with no row findings.
                </p>
              )}
            </div>
          )}

          {imports.isLoading ? (
            <LoadingState label="Loading import history" />
          ) : imports.data?.length ? (
            <div className="import-run-list">
              <p className="eyebrow">Recent runs</p>
              {imports.data.map((run) => (
                <button
                  className="import-run-row"
                  key={run.id}
                  onClick={() => { setActiveRun(run); setCommitResult(null); setError('') }}
                >
                  <span>
                    <strong>{run.source_name}</strong>
                    <small>{dateTime(run.created_at)}</small>
                  </span>
                  <StatusPill status={run.status} />
                  {!run.stored_workbook && <AlertTriangle size={17} />}
                </button>
              ))}
            </div>
          ) : null}

          {error && <p className="form-error">{error}</p>}
        </div>
      )}
    </article>
  )
}

export default function SettingsPage() {
  const { user } = useAuth()
  const administrator = user?.role === 'administrator'
  const users = useQuery({
    queryKey: ['users'],
    queryFn: () => apiFetch<User[]>('/auth/users'),
    enabled: administrator,
  })
  const devices = useQuery({ queryKey: ['devices'], queryFn: () => apiFetch<Device[]>('/devices') })
  const [editingAccount, setEditingAccount] = useState<User | null>(null)

  return (
    <div>
      <PageHeader
        eyebrow="Local administration"
        title="Settings"
        description="Appearance, the local account, workshop adapters, and print-safety preferences."
      />

      <section className="settings-grid">
        <AppearancePanel />

        <WorkbookImportPanel administrator={administrator} />

        <OperationalPolicyPanel administrator={administrator} />

        <article className="card settings-section settings-section--wide">
          <header className="card__header">
            <div>
              <p className="eyebrow">Local administrator</p>
              <h2><UserRound size={20} /> Account</h2>
            </div>
          </header>
          {!administrator ? (
            <p className="permission-note">
              <ShieldCheck size={18} /> Only the administrator can edit this account.
            </p>
          ) : users.isLoading ? (
            <LoadingState />
          ) : (
            <div className="user-list">
              {users.data?.slice(0, 1).map((account) => (
                <div className="user-row" key={account.id}>
                  <span className="account__avatar">{account.display_name.slice(0, 1).toUpperCase()}</span>
                  <div>
                    <strong>{account.display_name}</strong>
                    <small>@{account.username}</small>
                  </div>
                  <StatusPill status="active" label="Administrator" />
                  <span className="you-label">Only account</span>
                  <button className="icon-button" onClick={() => setEditingAccount(account)} aria-label="Edit account"><Pencil size={17} /></button>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="card settings-section settings-section--wide">
          <header className="card__header">
            <div>
              <p className="eyebrow">Future adapters</p>
              <h2><Smartphone size={20} /> Scales and NFC</h2>
            </div>
          </header>
          {devices.isLoading ? (
            <LoadingState />
          ) : !devices.data?.length ? (
            <EmptyState
              icon={Smartphone}
              title="No adapters registered"
              description={
                'The secure device model is ready for future scale and NFC adapters; '
                + 'manual weighing and QR labels are available now.'
              }
            />
          ) : (
            <div className="table-card table-card--embedded">
              <table>
                <thead>
                  <tr><th>Device</th><th>Type</th><th>Location</th><th>Status</th><th>Last seen</th></tr>
                </thead>
                <tbody>
                  {devices.data.map((device) => (
                    <tr key={device.id}>
                      <td>
                        <strong>{device.device_code}</strong>
                        <small className="table-subtext">
                          {device.firmware_version ?? 'Firmware unknown'}
                        </small>
                      </td>
                      <td>{titleCase(device.device_type)}</td>
                      <td>{device.location ?? '-'}</td>
                      <td><StatusPill status={device.enabled ? 'active' : 'disabled'} /></td>
                      <td>{dateTime(device.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      </section>

      {editingAccount ? <AccountEditorModal account={editingAccount} onClose={() => setEditingAccount(null)} /> : null}
    </div>
  )
}
