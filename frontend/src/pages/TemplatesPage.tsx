import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileInput, GitCompareArrows, Library, Pencil, Plus } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { apiFetch } from '../api/client'
import type {
  BuildPlate,
  CuraSettingCatalogItem,
  Filament,
  MaterialProfile,
  MaterialTemplate,
  Printer,
} from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { MaterialComparisonModal } from '../components/MaterialComparisonModal'
import { MaterialSettingsEditor, settingsFromForm, typedCuraKeys } from '../components/MaterialSettingsEditor'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../context/AuthContext'
import { Link } from '../context/RouterContext'

function nullable(value: FormDataEntryValue | null) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

export default function TemplatesPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [showEditor, setShowEditor] = useState(false)
  const [editSource, setEditSource] = useState<MaterialTemplate | null>(null)
  const [comparisonTargetKey, setComparisonTargetKey] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=true') })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const filaments = useQuery({ queryKey: ['filaments'], queryFn: () => apiFetch<Filament[]>('/filaments') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const catalog = useQuery({ queryKey: ['cura-settings-catalog'], queryFn: () => apiFetch<CuraSettingCatalogItem[]>('/profiles/cura-settings/catalog') })
  const save = useMutation({
    mutationFn: ({ form, template }: { form: HTMLFormElement; template: MaterialTemplate | null }) => {
      const data = new FormData(form)
      const settings = settingsFromForm(form, catalog.data ?? [])
      if (template) return apiFetch(`/profiles/templates/${template.id}/settings`, {
        method: 'PUT',
        body: JSON.stringify({ expected_template_version: template.record_version, settings }),
      })
      return apiFetch('/profiles/templates', {
        method: 'POST',
        body: JSON.stringify({
          name: `Template ${String(data.get('material_type')).trim()}`,
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
      setMessage('Template saved. Linked filament profiles inherited the changes except where values are explicitly customized, and Cura synchronization was queued automatically.')
      setShowEditor(false)
      setEditSource(null)
      await queryClient.invalidateQueries({ queryKey: ['material-templates'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const sourceSettings = editSource?.revisions[0]?.settings
  const loading = templates.isLoading || printers.isLoading || plates.isLoading || catalog.isLoading

  const openEditor = (template: MaterialTemplate) => {
    setEditSource(template)
    setShowEditor(true)
    setMessage('')
  }
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage('')
    save.mutate({ form: event.currentTarget, template: editSource })
  }

  return <div>
    <PageHeader eyebrow="Reusable inherited bases" title="Material templates" description="Templates synchronize to Cura under the Template brand. A direct template save immediately updates linked filament profiles while preserving their explicit customizations." actions={user && user.role !== 'viewer' ? <>{user.role === 'administrator' ? <Link className="button" to="/workstations"><FileInput size={17} /> Import from Cura</Link> : null}<button className="button button--primary" onClick={() => { setEditSource(null); setShowEditor(true); setMessage('') }}><Plus size={17} /> Add template</button></> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    {loading ? <LoadingState /> : !templates.data?.length ? <EmptyState icon={Library} title="No material templates" description="Add Template PLA, Template PETG, Template ASA, and the other material bases you use." /> : <div className="catalog-grid">{templates.data.map((template) => {
      const latest = template.revisions[0]
      return <article className="catalog-card catalog-card--template" key={template.id}><div><p className="eyebrow">{template.material_type} · {template.nozzle_diameter_mm} mm nozzle</p><h2>{template.name}</h2><p>{template.description ?? 'No description'}</p></div><dl className="catalog-meta"><div><dt>Printer</dt><dd>{printers.data?.find((item) => item.id === template.printer_id)?.name ?? 'Unknown'}</dd></div><div><dt>Linked behavior</dt><dd>Automatic inheritance</dd></div><div><dt>Temperatures</dt><dd>{latest.settings.extruder_temp_c}° / {latest.settings.bed_temp_c}°</dd></div><div><dt>Cura settings</dt><dd>{Object.keys(latest.settings.cura_extensions).length + typedCuraKeys.size} available</dd></div></dl><div className="template-card__actions">{profiles.data?.length ? <button className="button" onClick={() => setComparisonTargetKey(`template:${latest.id}`)}><GitCompareArrows size={16} /> Compare settings</button> : null}{user?.role !== 'viewer' && <button className="button" onClick={() => openEditor(template)}><Pencil size={16} /> Edit template</button>}</div></article>
    })}</div>}
    {comparisonTargetKey && profiles.data ? <MaterialComparisonModal
      profiles={profiles.data}
      templates={templates.data ?? []}
      printers={printers.data ?? []}
      filaments={filaments.data ?? []}
      plates={plates.data ?? []}
      catalog={catalog.data ?? []}
      initialTargetKey={comparisonTargetKey}
      onClose={() => setComparisonTargetKey(null)}
    /> : null}
    {showEditor ? <Modal title={editSource ? `Edit ${editSource.name}` : 'Add material template'} description={editSource ? 'Save current settings directly. Linked profiles inherit the change immediately unless a value is customized.' : 'Group the template identity and all Cura settings in one guided editor.'} onClose={() => { setShowEditor(false); setEditSource(null) }} size="wide" footer={<><button type="button" className="button" onClick={() => { setShowEditor(false); setEditSource(null) }}>Cancel</button><button type="submit" className="button button--primary" form="edit-material-template" disabled={save.isPending}>{editSource ? <Pencil size={17} /> : <Plus size={17} />}{save.isPending ? 'Saving…' : 'Save template'}</button></>}>
      <form id="edit-material-template" className="editor-form" onSubmit={submit} key={editSource?.revisions[0]?.id ?? 'new-template'}>
        {!editSource ? <EditorSection title="Template identity" description="Scope the reusable starting point to a printer, nozzle, and filament diameter.">
          <div className="form-grid">
            <label>Material type<input name="material_type" list="common-material-types" placeholder="PLA, PCTPE, Nylon 645…" required autoFocus /><small className="field-help">Cura name: Template + material type; brand: Template.</small><datalist id="common-material-types">{['PLA', 'PLA+', 'PETG', 'ASA', 'TPU', 'PCTPE', 'Nylon 645'].map((material) => <option key={material} value={material} />)}</datalist></label>
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
