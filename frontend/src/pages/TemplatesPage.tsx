import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileInput, GitCompareArrows, Library, Pencil, Plus } from 'lucide-react'
import { type FormEvent, type InvalidEvent, useEffect, useRef, useState } from 'react'
import { apiFetch, validationMessagesFor } from '../api/client'
import type {
  BuildPlate,
  CuraSettingCatalogItem,
  Filament,
  MaterialProfile,
  MaterialTemplate,
  Nozzle,
  Printer,
} from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { FormSubmissionError } from '../components/FormSubmissionError'
import { LoadingState } from '../components/LoadingState'
import { MaterialComparisonModal } from '../components/MaterialComparisonModal'
import { canonicalMaterialFieldCount, materialSettingLabel, MaterialSettingsEditor, settingsFromForm } from '../components/MaterialSettingsEditor'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../context/AuthContext'
import { Link } from '../context/RouterContext'
import { compactNumber } from '../lib/format'

function nullable(value: FormDataEntryValue | null) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

function centerAndFocus(control: HTMLElement) {
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  control.scrollIntoView({
    behavior: reduceMotion ? 'auto' : 'smooth',
    block: 'center',
    inline: 'nearest',
  })
  control.focus({ preventScroll: true })
}

export default function TemplatesPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [showEditor, setShowEditor] = useState(false)
  const [editSource, setEditSource] = useState<MaterialTemplate | null>(null)
  const [openingTemplateId, setOpeningTemplateId] = useState<string | null>(null)
  const [comparisonTargetKey, setComparisonTargetKey] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [newPrinterId, setNewPrinterId] = useState('')
  const [newNozzleId, setNewNozzleId] = useState('')
  const editorFormRef = useRef<HTMLFormElement>(null)
  const nativeInvalidPending = useRef(false)
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=true') })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const filaments = useQuery({ queryKey: ['filaments'], queryFn: () => apiFetch<Filament[]>('/filaments') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const nozzles = useQuery({ queryKey: ['nozzles'], queryFn: () => apiFetch<Nozzle[]>('/nozzles') })
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
          nozzle_id: String(data.get('nozzle_id')),
          nozzle_diameter_mm: nozzles.data?.find((nozzle) => nozzle.id === data.get('nozzle_id'))?.diameter_mm,
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
  })
  const sourceSettings = editSource?.revisions[0]?.settings
  const allValidationErrors = validationMessagesFor(save.error)
  const settingsValidationErrors = validationMessagesFor(save.error, 'settings')
  const identityError = (field: string) => allValidationErrors[field] ?? []
  const identityErrorId = (field: string) => `template-${field}-error`
  const identityFieldError = (field: string) => identityError(field).length ? (
    <span className="field-validation" id={identityErrorId(field)} role="alert">
      {identityError(field).map((error) => <span key={error}>{error}</span>)}
    </span>
  ) : null
  const hasValidationErrors = Object.keys(allValidationErrors).length > 0
  const loading = templates.isLoading || printers.isLoading || nozzles.isLoading || plates.isLoading || catalog.isLoading

  useEffect(() => {
    if (newPrinterId || !printers.data?.length) return
    setNewPrinterId(printers.data[0].id)
  }, [newPrinterId, printers.data])

  useEffect(() => {
    const compatible = (nozzles.data ?? []).filter((nozzle) => nozzle.printer_id === newPrinterId)
    if (compatible.some((nozzle) => nozzle.id === newNozzleId)) return
    setNewNozzleId(compatible[0]?.id ?? '')
  }, [newNozzleId, newPrinterId, nozzles.data])

  useEffect(() => {
    if (!hasValidationErrors) return undefined
    const frame = window.requestAnimationFrame(() => {
      const control = editorFormRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')
      if (control) centerAndFocus(control)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [hasValidationErrors, save.error])

  const closeEditor = () => {
    setShowEditor(false)
    setEditSource(null)
    save.reset()
  }
  const openEditor = async (template: MaterialTemplate) => {
    setMessage('')
    save.reset()
    setOpeningTemplateId(template.id)
    const refreshed = await templates.refetch()
    setOpeningTemplateId(null)
    const current = refreshed.data?.find((item) => item.id === template.id)
    if (!current) {
      setMessage('The template could not be refreshed. Reload the page and try again.')
      return
    }
    setEditSource(current)
    setShowEditor(true)
  }
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage('')
    save.mutate({ form: event.currentTarget, template: editSource })
  }
  const centerNativeInvalid = (event: InvalidEvent<HTMLFormElement>) => {
    if (nativeInvalidPending.current || !(event.target instanceof HTMLElement)) return
    nativeInvalidPending.current = true
    const control = event.target
    window.requestAnimationFrame(() => {
      centerAndFocus(control)
      nativeInvalidPending.current = false
    })
  }

  return <div>
    <PageHeader eyebrow="Reusable inherited bases" title="Material templates" description="Templates synchronize to Cura under the Template brand. A direct template save immediately updates linked filament profiles while preserving their explicit customizations." actions={user && user.role !== 'viewer' ? <>{user.role === 'administrator' ? <Link className="button" to="/workstations"><FileInput size={17} /> Import from Cura</Link> : null}<button className="button button--primary" onClick={() => { save.reset(); setEditSource(null); setShowEditor(true); setMessage('') }}><Plus size={17} /> Add template</button></> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    {loading ? <LoadingState /> : !templates.data?.length ? <EmptyState icon={Library} title="No material templates" description="Add Template PLA, Template PETG, Template ASA, and the other material bases you use." /> : <div className="catalog-grid">{templates.data.map((template) => {
      const latest = template.revisions[0]
      const nozzle = nozzles.data?.find((item) => item.id === template.nozzle_id)
      const printer = printers.data?.find((item) => item.id === template.printer_id)
      return <article className="catalog-card catalog-card--template" key={template.id}><div className="template-card__identity"><p className="eyebrow">{template.material_type} · {nozzle?.nozzle_code ?? 'Unknown nozzle'}</p><h2>{template.name}</h2><p>{printer?.name ?? 'Unknown printer'}</p></div><dl className="catalog-meta"><div><dt>Physical nozzle</dt><dd>{nozzle ? `${nozzle.nozzle_code} · ${compactNumber(nozzle.diameter_mm, 1)} mm ${nozzle.material}` : `${compactNumber(template.nozzle_diameter_mm, 1)} mm · unavailable`}</dd></div><div><dt>Linked behavior</dt><dd>Automatic inheritance</dd></div><div><dt>Temperatures</dt><dd>{compactNumber(latest.settings.extruder_temp_c, 0)}° / {compactNumber(latest.settings.bed_temp_c, 0)}°</dd></div><div><dt>Profile settings</dt><dd>{Object.keys(latest.settings.cura_extensions).length + canonicalMaterialFieldCount} unique controls</dd></div></dl><div className="template-card__actions">{profiles.data?.length ? <button className="button" onClick={() => setComparisonTargetKey(`template:${latest.id}`)}><GitCompareArrows size={16} /> Compare settings</button> : null}{user?.role !== 'viewer' && <button className="button" disabled={openingTemplateId === template.id} onClick={() => { void openEditor(template) }}><Pencil size={16} /> {openingTemplateId === template.id ? 'Refreshing…' : 'Edit template'}</button>}</div></article>
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
    {showEditor ? <Modal title={editSource ? `Edit ${editSource.name}` : 'Add material template'} description={editSource ? 'Save current settings directly. Linked profiles inherit the change immediately unless a value is customized.' : 'Group the template identity and all Cura settings in one guided editor.'} onClose={closeEditor} size="wide" footer={<><button type="button" className="button" onClick={closeEditor}>Cancel</button><button type="submit" className="button button--primary" form="edit-material-template" disabled={save.isPending}>{editSource ? <Pencil size={17} /> : <Plus size={17} />}{save.isPending ? 'Saving…' : 'Save template'}</button></>}>
      <form ref={editorFormRef} id="edit-material-template" className="editor-form" onSubmit={submit} onInvalid={centerNativeInvalid} key={editSource?.revisions[0]?.id ?? 'new-template'}>
        {!editSource ? <EditorSection title="Template identity" description="Scope the reusable starting point to a printer, nozzle, and filament diameter.">
          <div className="form-grid">
            <label>Material type<input name="material_type" list="common-material-types" placeholder="PLA, PCTPE, Nylon 645…" required autoFocus aria-invalid={identityError('material_type').length ? true : undefined} aria-describedby={identityError('material_type').length ? identityErrorId('material_type') : undefined} /><small className="field-help">Cura name: Template + material type; brand: Template.</small>{identityFieldError('material_type')}<datalist id="common-material-types">{['PLA', 'PLA+', 'PETG', 'ASA', 'TPU', 'PCTPE', 'Nylon 645'].map((material) => <option key={material} value={material} />)}</datalist></label>
            <label>Printer<select name="printer_id" value={newPrinterId} onChange={(event) => setNewPrinterId(event.target.value)} required aria-invalid={identityError('printer_id').length ? true : undefined} aria-describedby={identityError('printer_id').length ? identityErrorId('printer_id') : undefined}>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select>{identityFieldError('printer_id')}</label>
            <label>Physical nozzle<select name="nozzle_id" value={newNozzleId} onChange={(event) => setNewNozzleId(event.target.value)} required aria-invalid={identityError('nozzle_id').length ? true : undefined} aria-describedby={identityError('nozzle_id').length ? identityErrorId('nozzle_id') : undefined}><option value="" disabled>No nozzle available</option>{nozzles.data?.filter((nozzle) => nozzle.printer_id === newPrinterId).map((nozzle) => <option key={nozzle.id} value={nozzle.id}>{nozzle.nozzle_code} · {compactNumber(nozzle.diameter_mm, 1)} mm · {nozzle.material}</option>)}</select>{identityFieldError('nozzle_id')}</label>
            <label>Filament diameter<input name="filament_diameter_mm" type="number" min="0.1" step="0.01" defaultValue="1.75" required aria-invalid={identityError('filament_diameter_mm').length ? true : undefined} aria-describedby={identityError('filament_diameter_mm').length ? identityErrorId('filament_diameter_mm') : undefined} />{identityFieldError('filament_diameter_mm')}</label>
            <label className="form-grid__wide">Description<textarea name="description" rows={2} placeholder="Purpose, behavior, and calibration notes" aria-invalid={identityError('description').length ? true : undefined} aria-describedby={identityError('description').length ? identityErrorId('description') : undefined} />{identityFieldError('description')}</label>
          </div>
        </EditorSection> : null}
        <MaterialSettingsEditor
          settings={sourceSettings}
          validationErrors={settingsValidationErrors}
          catalog={catalog.data ?? []}
          plates={plates.data ?? []}
          copySources={(templates.data ?? []).filter((template) => template.active && template.id !== editSource?.id && template.revisions[0]).map((template) => ({
            id: template.id,
            label: `${template.name} · ${printers.data?.find((printer) => printer.id === template.printer_id)?.name ?? 'Unknown printer'} · ${compactNumber(template.nozzle_diameter_mm, 1)} mm`,
            settings: template.revisions[0].settings,
          }))}
          scope="template"
        />
        <FormSubmissionError
          error={save.error}
          fieldLabel={(field) => materialSettingLabel(field, catalog.data ?? [])}
          conflictMessage="This template changed after the editor opened. Close and reopen it to load the current values before saving."
        />
      </form>
    </Modal> : null}
  </div>
}
