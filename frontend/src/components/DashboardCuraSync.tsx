import { useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { CuraDeployment, WorkstationAgent } from '../api/types'
import { Modal } from './Modal'

/** Queue the same full-library operation as Workstations, without guessing a printer match. */
export function DashboardCuraSync() {
  const queryClient = useQueryClient()
  const [choices, setChoices] = useState<WorkstationAgent[] | null>(null)
  const sync = useMutation({
    mutationFn: async (agent: WorkstationAgent) => {
      const deployments = await apiFetch<CuraDeployment[]>(`/workstation-agents/${agent.id}/sync`, { method: 'POST' })
      if (!deployments.length) throw new Error('No synchronization request was queued. Try again from Cura Workstations.')
      return { deployments, name: agent.display_name }
    },
    onSuccess: ({ deployments }) => {
      queryClient.setQueryData<CuraDeployment[]>(['cura-deployments'], (current = []) => [
        ...deployments, ...current.filter(item => !deployments.some(updated => updated.id === item.id)),
      ])
      void queryClient.invalidateQueries({ queryKey: ['cura-deployments'] })
    },
  })
  const discover = useMutation({
    // Discover only on a deliberate click, using fresh eligibility, not dashboard polling.
    mutationFn: () => queryClient.fetchQuery({
      queryKey: ['workstation-agents'],
      queryFn: () => apiFetch<WorkstationAgent[]>('/workstation-agents'),
      staleTime: 0,
    }),
    onSuccess: (agents) => {
      const eligible = agents.filter(agent => agent.enabled && agent.cura_management_enabled && agent.cura_installations.length > 0)
      if (eligible.length === 1) sync.mutate(eligible[0])
      else setChoices(eligible)
    },
  })
  const pending = discover.isPending || sync.isPending
  return <div className="dashboard-cura-sync">
    <button type="button" className="button" disabled={pending} onClick={() => { sync.reset(); discover.mutate() }}>
      <RefreshCw size={17} />{pending ? 'Queueing…' : 'Sync to Cura'}
    </button>
    {sync.isSuccess && <p className="deployment-note" role="status">App settings queued for {sync.data.name}. Close Cura and wait for Succeeded in Cura Workstations before reopening. Offline agents receive the request after reconnecting.</p>}
    {(discover.error || sync.error) && <p className="form-error" role="alert">{(discover.error || sync.error)?.message}</p>}
    {choices !== null && <Modal title="Sync to Cura" description="Push the complete current app settings library, just like Push app settings in Cura Workstations. This action is not limited to the printer displayed on the Dashboard." onClose={() => setChoices(null)} footer={<button type="button" className="button" onClick={() => setChoices(null)}>Cancel</button>}>
      {choices.length ? <div className="dashboard-cura-sync__choices">
        <p>Choose a managed workstation. Cura must be closed before its agent applies the settings.</p>
        {choices.map(agent => <button type="button" className="button" key={agent.id} onClick={() => { setChoices(null); sync.mutate(agent) }}>Sync to {agent.display_name}</button>)}
      </div> : <p>No eligible managed Cura workstation is available. In Cura Workstations, enable a paired workstation, complete takeover, and wait for its agent to report a Cura installation.</p>}
    </Modal>}
  </div>
}
