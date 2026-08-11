import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  FileSpreadsheet,
  KeyRound,
  Plus,
  ShieldCheck,
  Smartphone,
  Upload,
  Users,
} from 'lucide-react'
import { type ChangeEvent, type FormEvent, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import type {
  Device,
  User,
  UserRole,
  WorkbookImportCounts,
  WorkbookImportRun,
} from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime, titleCase } from '../lib/format'

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const client = useQueryClient()
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('operator')
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: () => apiFetch<User>('/auth/users', {
      method: 'POST',
      body: JSON.stringify({ username, display_name: displayName, password, role }),
    }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Could not create user'),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    mutation.mutate()
  }

  return (
    <Modal
      title="Create local account"
      description="Assign only the access this person needs. Passwords are stored as Argon2id hashes."
      onClose={onClose}
      footer={(
        <>
          <button className="button" onClick={onClose}>Cancel</button>
          <button className="button button--primary" form="create-user" disabled={mutation.isPending}>
            Create account
          </button>
        </>
      )}
    >
      <form id="create-user" className="form-stack" onSubmit={submit}>
        <div className="form-grid">
          <label>
            Username
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              minLength={3}
              maxLength={80}
              autoComplete="off"
              required
            />
          </label>
          <label>
            Display name
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              maxLength={120}
              required
            />
          </label>
        </div>
        <label>
          Role
          <select value={role} onChange={(event) => setRole(event.target.value as UserRole)}>
            <option value="administrator">Administrator</option>
            <option value="operator">Operator</option>
            <option value="viewer">Viewer</option>
          </select>
          <small className="field-help">
            Administrators manage users and overrides. Operators update workshop data. Viewers are read-only.
          </small>
        </label>
        <label>
          Temporary password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={14}
            maxLength={256}
            autoComplete="new-password"
            required
          />
          <small className="field-help">Use at least 14 characters. Share it through a secure channel.</small>
        </label>
        {error && <p className="form-error">{error}</p>}
      </form>
    </Modal>
  )
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
                  {commitResult.profiles} draft profiles.
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
  const [creating, setCreating] = useState(false)

  return (
    <div>
      <PageHeader
        eyebrow="Local administration"
        title="Settings"
        description="Accounts, future workshop adapters, and the security posture of this installation."
        actions={administrator ? (
          <button className="button button--primary" onClick={() => setCreating(true)}>
            <Plus size={17} /> Add account
          </button>
        ) : undefined}
      />

      <section className="settings-grid">
        <WorkbookImportPanel administrator={administrator} />

        <article className="card settings-section settings-section--wide">
          <header className="card__header">
            <div>
              <p className="eyebrow">Local roles</p>
              <h2><Users size={20} /> Accounts</h2>
            </div>
          </header>
          {!administrator ? (
            <p className="permission-note">
              <ShieldCheck size={18} /> Only administrators can inspect or create local accounts.
            </p>
          ) : users.isLoading ? (
            <LoadingState />
          ) : (
            <div className="user-list">
              {users.data?.map((account) => (
                <div className="user-row" key={account.id}>
                  <span className="account__avatar">{account.display_name.slice(0, 1).toUpperCase()}</span>
                  <div>
                    <strong>{account.display_name}</strong>
                    <small>@{account.username}</small>
                  </div>
                  <StatusPill
                    status={account.is_active ? 'active' : 'disabled'}
                    label={titleCase(account.role)}
                  />
                  {account.id === user?.id && <span className="you-label">You</span>}
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="card settings-section">
          <header className="card__header">
            <div>
              <p className="eyebrow">Security defaults</p>
              <h2><ShieldCheck size={20} /> Protected by design</h2>
            </div>
          </header>
          <ul className="feature-list">
            <li>
              <KeyRound size={17} />
              <span>
                <strong>Argon2id credentials</strong>
                <small>Local password hashes; no default account.</small>
              </span>
            </li>
            <li>
              <ShieldCheck size={17} />
              <span>
                <strong>Revocable sessions</strong>
                <small>HttpOnly cookies, CSRF binding, idle expiry.</small>
              </span>
            </li>
            <li>
              <ShieldCheck size={17} />
              <span>
                <strong>Least privilege</strong>
                <small>Administrator, Operator, and Viewer enforcement.</small>
              </span>
            </li>
          </ul>
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

      {creating && <CreateUserModal onClose={() => setCreating(false)} />}
    </div>
  )
}
