import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Power } from 'lucide-react'
import { apiFetch } from '../api/client'

/** Request power on without treating acceptance as Klipper readiness. */
export function PrinterPowerButton({ printerId }: { printerId: string }) {
  const client = useQueryClient()
  const power = useMutation({
    mutationFn: () => apiFetch(`/printers/${printerId}/power-on`, { method: 'POST' }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ['dashboard'] }) },
  })
  return <div className="printer-power-control">
    <button className="button" disabled={power.isPending || power.isSuccess} onClick={() => power.mutate()}><Power size={17} />{power.isPending ? 'Powering on…' : power.isSuccess ? 'Power on accepted' : 'Power on'}</button>
    {power.isSuccess && <small role="status">Waiting for printer status to refresh.</small>}
    {power.error && <small className="form-error" role="alert">{power.error.message}</small>}
  </div>
}
