import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { actionableApiError, apiFetch } from '../api/client'
import type { PrintJob } from '../api/types'
import { Modal } from './Modal'

interface GcodePage { text: string; page: number; total_pages: number; size_bytes: number; sha256: string }

/** Read-only original files and explicitly confirmed local history repair. */
export function PrintHistoryActions({ job, canManage }: { job: PrintJob; canManage: boolean }) {
  const client = useQueryClient()
  const [viewing, setViewing] = useState(false)
  const [confirmClose, setConfirmClose] = useState(false)
  const [page, setPage] = useState(1)
  const content = useQuery({ queryKey: ['print-gcode', job.id, page], queryFn: () => apiFetch<GcodePage>(`/prints/${job.id}/gcode?page=${page}`), enabled: viewing })
  const refresh = async () => { await client.invalidateQueries({ queryKey: ['prints'] }) }
  const capture = useMutation({ mutationFn: () => apiFetch(`/prints/${job.id}/gcode/capture`, { method: 'POST' }), onSuccess: refresh })
  const close = useMutation({
    mutationFn: () => apiFetch(`/prints/${job.id}/close-stale`, { method: 'POST', body: JSON.stringify({ expected_version: job.record_version }) }),
    onSuccess: async () => { setConfirmClose(false); await refresh() },
  })
  return <section>
    <p className="eyebrow">Saved G-code</p>
    <div className="print-gcode-actions">
      {job.gcode_saved ? <>
        <button className="button" onClick={() => setViewing(true)}>View G-code</button>
        <a className="button" href={`/api/v1/prints/${job.id}/gcode?download=true`}>Download G-code</a>
      </> : <>
        <span className="muted">No verified copy saved. Files over 100 MB are not retained.</span>
        {canManage && job.gcode_sha256 ? <button className="button" disabled={capture.isPending} onClick={() => capture.mutate()}>{capture.isPending ? 'Verifying…' : 'Retrieve verified original'}</button> : null}
      </>}
      {canManage && job.status === 'in_progress' ? <button className="button" onClick={() => setConfirmClose(true)}>Close stale entry</button> : null}
    </div>
    {capture.error ? <p className="form-error">{actionableApiError(capture.error)}</p> : null}
    {confirmClose ? <Modal title="Close stale history entry?" onClose={() => setConfirmClose(false)}>
      <p>The printer must be reachable and idle. This marks only this entry as interrupted with an unknown outcome. It does not cancel a print, invent an end time, or subtract filament.</p>
      {close.error ? <p className="form-error">{actionableApiError(close.error)}</p> : null}
      <div className="print-gcode-actions"><button className="button" disabled={close.isPending} onClick={() => setConfirmClose(false)}>Keep entry open</button>
      <button className="button button--primary" disabled={close.isPending} onClick={() => close.mutate()}>Verify idle and close entry</button></div>
    </Modal> : null}
    {viewing ? <Modal title="Saved G-code" size="wide" onClose={() => setViewing(false)}>
      <p className="muted">Read-only original. Pages contain 32 KB of text; a line may continue on the next page. Downloads preserve the original bytes.</p>
      {content.isPending ? <p>Loading…</p> : content.error ? <p className="form-error">{actionableApiError(content.error)}</p> : content.data ? <>
        <div className="print-gcode-actions">
          <button className="button" disabled={page <= 1} onClick={() => setPage(1)}>First</button>
          <button className="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {content.data.page} of {content.data.total_pages}</span>
          <button className="button" disabled={page >= content.data.total_pages} onClick={() => setPage(page + 1)}>Next</button>
          <button className="button" disabled={page >= content.data.total_pages} onClick={() => setPage(content.data!.total_pages)}>Last</button>
        </div>
        <pre className="print-gcode-text">{content.data.text}</pre>
      </> : null}
    </Modal> : null}
  </section>
}
