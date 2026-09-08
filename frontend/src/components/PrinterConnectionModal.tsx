import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, actionableApiError } from '../api/client'
import type { Printer } from '../api/types'
import { LoadingState } from './LoadingState'
import { Modal } from './Modal'

interface Connection {
  base_url: string
  enabled: boolean
  managed: boolean
  has_api_key: boolean
  record_version: number
}

/** Administrator-only connection editor. Secrets are write-only and never cached. */
export function PrinterConnectionModal({ printer, onClose }: { printer?: Printer; onClose: () => void }) {
  const client = useQueryClient()
  const connection = useQuery({
    queryKey: ['printer-connection', printer?.id],
    queryFn: () => apiFetch<Connection>(`/printers/${printer!.id}/connection`),
    enabled: Boolean(printer),
    gcTime: 0,
  })
  const save = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form)
      const key = String(data.get('api_key') ?? '').trim()
      // React Query retains mutation variables for retries/history. Never leave
      // a secret in the retained form element after reading the outgoing value.
      const keyInput = form.elements.namedItem('api_key')
      if (keyInput instanceof HTMLInputElement) keyInput.value = ''
      return apiFetch(printer ? `/printers/${printer.id}/connection` : '/printers', {
        method: printer ? 'PUT' : 'POST',
        body: JSON.stringify({
          base_url: String(data.get('base_url') ?? '').trim(),
          enabled: data.get('enabled') === 'on',
          ...(key ? { api_key: key } : {}),
          ...(printer ? { expected_version: connection.data?.record_version, clear_api_key: data.get('clear_api_key') === 'on' }
            : { name: String(data.get('name') ?? '').trim(), extruder_count: Number(data.get('extruder_count') ?? 1) }),
        }),
      })
    },
    onSuccess: () => {
      onClose()
      void client.invalidateQueries({ queryKey: ['printers'] })
      void client.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  return <Modal title={printer ? `${printer.name} connection` : 'Add 3D printer'} onClose={onClose} footer={<>
    <button className="button" type="button" onClick={onClose}>Cancel</button>
    <button className="button button--primary" form="printer-connection" disabled={save.isPending || Boolean(printer && !connection.data)}>{save.isPending ? 'Saving…' : 'Save printer'}</button>
  </>}>
    {printer && connection.isLoading ? <LoadingState /> : printer && !connection.data ? <p className="form-error" role="alert">Connection settings could not be loaded. Close and try again.</p> : <form id="printer-connection" className="editor-form" onSubmit={(event) => { event.preventDefault(); save.mutate(event.currentTarget) }}>
      {!printer && <div className="form-grid">
        <label>Printer name<input name="name" required maxLength={160} autoFocus /></label>
        <label>Independent hotends<input name="extruder_count" type="number" min={1} max={16} step={1} defaultValue={1} required /></label>
      </div>}
      <label>Moonraker URL<input name="base_url" type="url" required maxLength={512} placeholder="http://printer.local:7125" defaultValue={connection.data?.base_url ?? ''} autoComplete="off" /></label>
      <label>Moonraker API key<input name="api_key" type="password" maxLength={4096} autoComplete="new-password" placeholder={connection.data?.has_api_key ? 'Leave blank to keep the saved key' : 'Optional for a trusted Moonraker client'} /></label>
      {connection.data?.has_api_key && <label className="check-row"><input name="clear_api_key" type="checkbox" />Remove the saved API key</label>}
      <label className="check-row"><input name="enabled" type="checkbox" defaultChecked={connection.data?.enabled ?? true} />Enable this connection</label>
      <p className="security-note">Use a trusted printer network or verified HTTPS. API keys are encrypted in the database; keep the private application data volume and its encryption key backed up separately. Changing the endpoint or disabling a connection requires a confirmed idle printer.</p>
      {printer && !connection.data?.managed && <p className="deployment-note">Saving adopts this existing printer connection into app settings. Later deployment-variable changes will not overwrite it.</p>}
      {save.error && <p className="form-error" role="alert">{actionableApiError(save.error)}</p>}
    </form>}
  </Modal>
}
