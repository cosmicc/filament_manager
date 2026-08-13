import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CopyPlus, Library, Plus, Upload } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { apiFetch } from '../api/client'
import type {
  BuildPlate,
  CuraSettingCatalogItem,
  MaterialTemplate,
  Printer,
} from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { MaterialSettingsEditor, settingsFromForm, typedCuraKeys } from '../components/MaterialSettingsEditor'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'

function nullable(value: FormDataEntryValue | null) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

export default function TemplatesPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [showEditor, setShowEditor] = useState(false)
  const [revisionSource, setRevisionSource] = useState<MaterialTemplate | null>(null)
  const [message, setMessage] = useState('')
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=true') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const catalog = useQuery({ queryKey: ['cura-settings-catalog'], queryFn: () => apiFetch<CuraSettingCatalogItem[]>('/profiles/cura-settings/catalog') })
  const save = useMutation({
    mutationFn: ({ form, template }: { form: HTMLFormElement; template: MaterialTemplate | null }) => {
      const data = new FormData(form)
      const settings = settingsFromForm(form, catalog.data ?? [])
      if (template) return apiFetch(`/profiles/templates/${template.id}/revisions`, {
        method: 'POST',
        body: JSON.stringify({ expected_template_version: template.record_version, settings }),
      })
      return apiFetch('/profiles/templates', {
        method: 'POST',
        body: JSON.stringify({
          name: String(data.get('name')).trim(),
          material_type: String(data.get('material_type')).trim(),
          description: nullable(data.get('description')),
          printer_id: String(data.get('printer_id')),
          nozzle_diameter_mm: String(data.get('nozzle_diameter_mm')),
          filament_diameter_mm: String(data.get('filament_diameter_mm')),
          settings,
        }),
      })
    },
    onSuccess: async () => {
      setMessage('Draft template revision saved. Publish it when the settings are ready for new filaments and Cura.')
      setShowEditor(false)
      setRevisionSource(null)
      await queryClient.invalidateQueries({ queryKey: ['material-templates'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const publish = useMutation({
    mutationFn: ({ templateId, revisionId }: { templateId: string; revisionId: string }) => apiFetch(`/profiles/templates/${templateId}/revisions/${revisionId}/publish`, { method: 'POST' }),
    onSuccess: async () => {
      setMessage('Template revision published and Cura synchronization queued for managed workstations.')
      await queryClient.invalidateQueries({ queryKey: ['material-templates'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const sourceSettings = revisionSource?.revisions[0]?.settings
  const loading = templates.isLoading || printers.isLoading || plates.isLoading || catalog.isLoading

  const openNewRevision = (template: MaterialTemplate) => {
    setRevisionSource(template)
    setShowEditor(true)
    setMessage('')
  }
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage('')
    save.mutate({ form: event.currentTarget, template: revisionSource })
  }

  return <div>
    <PageHeader eyebrow="Reusable starting points" title="Material templates" description="Create printer- and nozzle-specific generic materials. New filament products copy a published revision and can then be tuned independently." actions={user?.role !== 'viewer' ? <button className="button button--primary" onClick={() => { setRevisionSource(null); setShowEditor(true); setMessage('') }}><Plus size={17} /> Add template</button> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    {loading ? <LoadingState /> : !templates.data?.length ? <EmptyState icon={Library} title="No material templates" description="Add Generic PLA, PETG, ASA, PLA+, TPU, PCTPE, Nylon 645, and any other starting materials you use." /> : <div className="catalog-grid">{templates.data.map((template) => {
      const latest = template.revisions[0]
      return <article className="catalog-card catalog-card--template" key={template.id}><div><p className="eyebrow">{template.material_type} · {template.nozzle_diameter_mm} mm nozzle</p><h2>{template.name}</h2><p>{template.description ?? 'No description'}</p></div><dl className="catalog-meta"><div><dt>Printer</dt><dd>{printers.data?.find((item) => item.id === template.printer_id)?.name ?? 'Unknown'}</dd></div><div><dt>Revision</dt><dd>v{latest.version}</dd></div><div><dt>Temperatures</dt><dd>{latest.settings.extruder_temp_c}° / {latest.settings.bed_temp_c}°</dd></div><div><dt>Cura settings</dt><dd>{Object.keys(latest.settings.cura_extensions).length + typedCuraKeys.size} available</dd></div></dl><div className="template-card__actions"><StatusPill status={latest.status} />{user?.role !== 'viewer' && latest.status !== 'published' && <button className="button button--primary" disabled={publish.isPending} onClick={() => publish.mutate({ templateId: template.id, revisionId: latest.id })}><Upload size={16} /> Publish v{latest.version}</button>}{user?.role !== 'viewer' && <button className="button" onClick={() => openNewRevision(template)}><CopyPlus size={16} /> New revision</button>}</div></article>
    })}</div>}
    {showEditor ? <Modal title={revisionSource ? `New ${revisionSource.name} revision` : 'Add material template'} description={revisionSource ? 'Copy the latest settings into a new draft revision and adjust them.' : 'Group the template identity and all Cura settings in one guided editor.'} onClose={() => { setShowEditor(false); setRevisionSource(null) }} size="wide" footer={<><button type="button" className="button" onClick={() => { setShowEditor(false); setRevisionSource(null) }}>Cancel</button><button type="submit" className="button button--primary" form="edit-material-template" disabled={save.isPending}>{revisionSource ? <CopyPlus size={17} /> : <Plus size={17} />}{save.isPending ? 'Saving…' : revisionSource ? 'Save new revision' : 'Save template'}</button></>}>
      <form id="edit-material-template" className="editor-form" onSubmit={submit} key={revisionSource?.revisions[0]?.id ?? 'new-template'}>
        {!revisionSource ? <EditorSection title="Template identity" description="Scope the reusable starting point to a printer, nozzle, and filament diameter.">
          <div className="form-grid">
            <label>Template name<input name="name" placeholder="Generic PLA" required autoFocus /></label>
            <label>Material type<input name="material_type" list="common-material-types" placeholder="PLA, PCTPE, Nylon 645…" required /><datalist id="common-material-types">{['PLA', 'PLA+', 'PETG', 'ASA', 'TPU', 'PCTPE', 'Nylon 645'].map((material) => <option key={material} value={material} />)}</datalist></label>
            <label>Printer<select name="printer_id" required>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label>
            <label>Nozzle diameter<input name="nozzle_diameter_mm" type="number" min="0.1" step="0.05" defaultValue={printers.data?.[0]?.nozzle_diameter_mm ?? '0.4'} required /></label>
            <label>Filament diameter<input name="filament_diameter_mm" type="number" min="0.1" step="0.01" defaultValue="1.75" required /></label>
            <label className="form-grid__wide">Description<textarea name="description" rows={2} placeholder="Purpose, behavior, and calibration notes" /></label>
          </div>
        </EditorSection> : null}
        <MaterialSettingsEditor settings={sourceSettings} catalog={catalog.data ?? []} plates={plates.data ?? []} />
        {save.error ? <p className="form-error" role="alert">{save.error.message}</p> : null}
      </form>
    </Modal> : null}
  </div>
}
