import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import type { Filament, MaterialProfile, MaterialTemplate } from '../api/types'
import { Modal } from './Modal'

/** Change the inheritance source, keeping custom values and historical snapshots. */
export function ChangeFilamentTemplateModal({ filament, profile, templates, onClose }: {
  filament: Filament
  profile: MaterialProfile
  templates: MaterialTemplate[]
  onClose: () => void
}) {
  const client = useQueryClient()
  const [targetId, setTargetId] = useState('')
  const options = templates.filter((template) => template.active && template.printer_id === profile.printer_id
    && Number(template.nozzle_diameter_mm) === Number(profile.nozzle_diameter_mm)
    && template.revisions[0] && template.revisions[0].id !== profile.base_template_revision_id)
  const target = options.find((template) => template.revisions[0].id === targetId)
  const save = useMutation({
    mutationFn: () => apiFetch<MaterialProfile>(`/profiles/${profile.id}/change-template`, {
      method: 'POST', body: JSON.stringify({ expected_profile_version: profile.record_version,
        expected_filament_version: filament.record_version, target_template_revision_id: targetId }),
    }),
    onSuccess: async () => {
      await Promise.all([['profiles'], ['filaments'], ['filament', filament.id], ['spools']]
        .map((queryKey) => client.invalidateQueries({ queryKey })))
      onClose()
    },
  })
  return <Modal title="Change template" description="Custom print-setting values are preserved. All inherited settings will use the new template. Prior print history remains unchanged."
    onClose={() => { if (!save.isPending) onClose() }}
    footer={<><button className="button" disabled={save.isPending} onClick={onClose}>Cancel</button><button className="button button--primary" disabled={!targetId || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Change template'}</button></>}>
    <label>New template<select value={targetId} disabled={save.isPending} onChange={(event) => setTargetId(event.target.value)} autoFocus>
      <option value="">Choose a template</option>
      {options.map((template) => <option key={template.id} value={template.revisions[0].id}>{template.name} · {template.nozzle_diameter_mm} mm</option>)}
    </select></label>
    {!options.length ? <p>No other active template exists for this printer and nozzle diameter. Add one on the Templates page first.</p> : null}
    {target && target.material_type.toLowerCase() !== filament.material_type.toLowerCase() ? <p className="security-note">This corrects the filament type from {filament.material_type} to {target.material_type}, including its spool names. Other print-settings scopes must have matching templates for the new material; their custom values are also preserved.</p> : null}
    <p className="muted">{profile.override_keys.length} custom {profile.override_keys.length === 1 ? 'value' : 'values'} will be reapplied. A value equal to its new default will be shown as inherited.</p>
    {save.error ? <p className="form-error" role="alert">{save.error.message}</p> : null}
  </Modal>
}
