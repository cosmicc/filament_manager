import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Download, FileUp, GitCompareArrows, Library, Pencil, Plus, Trash2 } from 'lucide-react'
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
import { CollectionViewSelector } from '../components/CollectionViewSelector'
import { EmptyState } from '../components/EmptyState'
import { FormSubmissionError } from '../components/FormSubmissionError'
import { LoadingState } from '../components/LoadingState'
import { MaterialComparisonModal } from '../components/MaterialComparisonModal'
import { materialSettingLabel, MaterialSettingsEditor, settingsFromForm } from '../components/MaterialSettingsEditor'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../context/AuthContext'
import { useCollectionView } from '../hooks/useCollectionView'
import { compactNumber } from '../lib/format'

interface PortableTemplateDocument {
  schema_version: 1
  kind: 'filament_manager_material_template'
  template: {
    material_type: string
    name: string
    description: string | null
    filament_diameter_mm: string
    preferred_build_plate_surface_code?: string | null
    settings: MaterialTemplate['revisions'][number]['settings']
  }
}

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
  const [view, setView] = useCollectionView('templates', 'cards')
  const [showImport, setShowImport] = useState(false)
  const [importDocument, setImportDocument] = useState<PortableTemplateDocument | null>(null)
  const [importFileError, setImportFileError] = useState('')
  const [importMode, setImportMode] = useState<'create' | 'overwrite'>('create')
  const [importTargetId, setImportTargetId] = useState('')
  const [importPrinterId, setImportPrinterId] = useState('')
  const [importNozzleId, setImportNozzleId] = useState('')
  const [importMaterialType, setImportMaterialType] = useState('')
  const [confirmOverwrite, setConfirmOverwrite] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<MaterialTemplate | null>(null)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')
  const editorFormRef = useRef<HTMLFormElement>(null)
  const nativeInvalidPending = useRef(false)
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates') })
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
        body: JSON.stringify({
          expected_template_version: template.record_version,
          material_type: String(data.get('material_type')).trim(),
          description: nullable(data.get('description')),
          printer_id: String(data.get('printer_id')),
          nozzle_id: String(data.get('nozzle_id')),
          nozzle_diameter_mm: nozzles.data?.find((nozzle) => nozzle.id === data.get('nozzle_id'))?.diameter_mm,
          filament_diameter_mm: String(data.get('filament_diameter_mm')),
          settings,
        }),
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
  const deleteTemplate = useMutation({
    mutationFn: (template: MaterialTemplate) => apiFetch<MaterialTemplate>(`/profiles/templates/${template.id}`, {
      method: 'DELETE',
      body: JSON.stringify({ expected_version: template.record_version, confirmation_name: deleteConfirmation }),
    }),
    onSuccess: async (template) => {
      setDeleteTarget(null)
      setDeleteConfirmation('')
      setMessage(`${template.name} was deleted from active templates and Cura. Its immutable history and existing filament snapshots were retained.`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['material-templates'] }),
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
      ])
    },
  })
  const importTemplate = useMutation({
    mutationFn: () => {
      if (!importDocument) throw new Error('Choose a Filament Manager template JSON file')
      const target = templates.data?.find((template) => template.id === importTargetId)
      return apiFetch<MaterialTemplate>('/profiles/templates/imports', {
        method: 'POST',
        body: JSON.stringify({
          mode: importMode,
          document: importDocument,
          target_template_id: importMode === 'overwrite' ? importTargetId : null,
          expected_template_version: importMode === 'overwrite' ? target?.record_version : null,
          printer_id: importMode === 'create' ? importPrinterId : null,
          nozzle_id: importMode === 'create' ? importNozzleId : null,
          material_type: importMode === 'create' ? importMaterialType : null,
          confirmed: importMode === 'overwrite' ? confirmOverwrite : false,
        }),
      })
    },
    onSuccess: async (template) => {
      setMessage(importMode === 'overwrite' ? `${template.name} was overwritten from the selected JSON file. Linked filament settings and Cura synchronization were updated.` : `${template.name} was created from the selected JSON file and queued for Cura synchronization.`)
      setShowImport(false)
      setImportDocument(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['material-templates'] }),
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
      ])
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
    const installed = printers.data.find((printer) => printer.active_nozzle_id)
    setNewPrinterId(installed?.id ?? printers.data[0].id)
  }, [newPrinterId, printers.data])

  useEffect(() => {
    const compatible = (nozzles.data ?? []).filter((nozzle) => nozzle.printer_id === newPrinterId)
    if (compatible.some((nozzle) => nozzle.id === newNozzleId)) return
    const installedNozzleId = printers.data?.find((printer) => printer.id === newPrinterId)?.active_nozzle_id
    setNewNozzleId(compatible.find((nozzle) => nozzle.id === installedNozzleId)?.id ?? compatible[0]?.id ?? '')
  }, [newNozzleId, newPrinterId, nozzles.data, printers.data])

  useEffect(() => {
    if (!importPrinterId && printers.data?.length) setImportPrinterId(printers.data[0].id)
  }, [importPrinterId, printers.data])

  useEffect(() => {
    const compatible = (nozzles.data ?? []).filter((nozzle) => nozzle.printer_id === importPrinterId)
    if (!compatible.some((nozzle) => nozzle.id === importNozzleId)) setImportNozzleId(compatible[0]?.id ?? '')
  }, [importNozzleId, importPrinterId, nozzles.data])

  useEffect(() => {
    if (!importTargetId && templates.data?.length) setImportTargetId(templates.data[0].id)
  }, [importTargetId, templates.data])

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
  const openNewEditor = () => {
    const defaultPrinter = printers.data?.find((printer) => printer.active_nozzle_id) ?? printers.data?.[0]
    const defaultNozzle = nozzles.data?.find((nozzle) => nozzle.id === defaultPrinter?.active_nozzle_id)
      ?? nozzles.data?.find((nozzle) => nozzle.printer_id === defaultPrinter?.id)
    save.reset()
    setEditSource(null)
    setNewPrinterId(defaultPrinter?.id ?? '')
    setNewNozzleId(defaultNozzle?.id ?? '')
    setShowEditor(true)
    setMessage('')
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
    setNewPrinterId(current.printer_id)
    setNewNozzleId(current.nozzle_id)
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
  const readImportFile = async (file: File | undefined) => {
    setImportFileError('')
    setImportDocument(null)
    importTemplate.reset()
    if (!file) return
    if (file.size > 256 * 1024) {
      setImportFileError('Template files must be 256 KB or smaller.')
      return
    }
    try {
      const parsed = JSON.parse(await file.text()) as Partial<PortableTemplateDocument>
      if (parsed.schema_version !== 1 || parsed.kind !== 'filament_manager_material_template' || !parsed.template || typeof parsed.template.material_type !== 'string' || typeof parsed.template.settings !== 'object') {
        throw new Error('This is not a supported Filament Manager template export.')
      }
      const document = parsed as PortableTemplateDocument
      setImportDocument(document)
      setImportMaterialType(document.template.material_type)
    } catch (error) {
      setImportFileError(error instanceof Error ? error.message : 'The template file could not be read.')
    }
  }

  return <div>
    <PageHeader eyebrow="Reusable inherited bases" title="Material templates" description="Templates synchronize to Cura under the Template brand. A direct template save immediately updates linked filament profiles while preserving their explicit customizations." actions={user && user.role !== 'viewer' ? <><button className="button" onClick={() => { importTemplate.reset(); setImportFileError(''); setShowImport(true) }}><FileUp size={17} /> Import template</button><button className="button button--primary" onClick={openNewEditor}><Plus size={17} /> Add template</button></> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    <section className="toolbar"><CollectionViewSelector label="Templates" value={view} onChange={setView} /><span className="toolbar__summary">{templates.data?.length ?? 0} templates</span></section>
    {loading ? <LoadingState /> : !templates.data?.length ? <EmptyState icon={Library} title="No material templates" description="Add Template PLA, Template PETG, Template ASA, and the other material bases you use." /> : view === 'list' ? <div className="table-card collection-table"><table><thead><tr><th>Template</th><th>Printer / nozzle</th><th>Temperatures</th><th>Material flow</th><th>Actions</th></tr></thead><tbody>{templates.data.map((template) => { const latest = template.revisions[0]; const nozzle = nozzles.data?.find((item) => item.id === template.nozzle_id); const printer = printers.data?.find((item) => item.id === template.printer_id); return <tr key={template.id}><td><strong>{template.name}</strong><small className="table-subtext">{template.material_type}</small></td><td>{printer?.name ?? 'Unknown printer'}<small className="table-subtext">{nozzle ? `${nozzle.nozzle_code} · ${compactNumber(nozzle.diameter_mm, 1)} mm` : 'Unknown nozzle'}</small></td><td>{compactNumber(latest.settings.extruder_temp_c, 0)}° / {compactNumber(latest.settings.bed_temp_c, 0)}°</td><td>{compactNumber(latest.settings.flow_percent, 0)}%</td><td><div className="table-actions">{profiles.data?.length ? <button className="icon-button" onClick={() => setComparisonTargetKey(`template:${latest.id}`)} title="Compare settings" aria-label={`Compare ${template.name}`}><GitCompareArrows size={17} /></button> : null}<a className="icon-button" href={`/api/v1/profiles/templates/${template.id}/exports/json`} title="Export template JSON" aria-label={`Export ${template.name}`}><Download size={17} /></a>{user?.role !== 'viewer' ? <><button className="icon-button" disabled={openingTemplateId === template.id} onClick={() => { void openEditor(template) }} title="Edit template" aria-label={`Edit ${template.name}`}><Pencil size={17} /></button><button className="icon-button" onClick={() => { deleteTemplate.reset(); setDeleteConfirmation(''); setDeleteTarget(template) }} title="Delete template" aria-label={`Delete ${template.name}`}><Trash2 size={17} /></button></> : null}</div></td></tr>})}</tbody></table></div> : <section className={`collection-grid collection-grid--${view}`}>{templates.data.map((template) => {
      const latest = template.revisions[0]
      const nozzle = nozzles.data?.find((item) => item.id === template.nozzle_id)
      const printer = printers.data?.find((item) => item.id === template.printer_id)
      return <article className={`catalog-card catalog-card--template${view === 'detailed' ? ' collection-card--detailed' : ''}`} key={template.id}><div className="template-card__identity"><p className="eyebrow">{template.material_type} · {nozzle?.nozzle_code ?? 'Unknown nozzle'}</p><h2>{template.name}</h2><p>{printer?.name ?? 'Unknown printer'}</p></div><dl className="catalog-meta"><div><dt>Physical nozzle</dt><dd>{nozzle ? `${nozzle.nozzle_code} · ${compactNumber(nozzle.diameter_mm, 1)} mm ${nozzle.material}` : `${compactNumber(template.nozzle_diameter_mm, 1)} mm · unavailable`}</dd></div><div><dt>Linked behavior</dt><dd>Automatic inheritance</dd></div><div><dt>Temperatures</dt><dd>{compactNumber(latest.settings.extruder_temp_c, 0)}° / {compactNumber(latest.settings.bed_temp_c, 0)}°</dd></div><div><dt>Material flow</dt><dd>{compactNumber(latest.settings.flow_percent, 0)}%</dd></div>{view === 'detailed' ? <><div><dt>Filament diameter</dt><dd>{compactNumber(template.filament_diameter_mm, 2)} mm</dd></div><div><dt>Status</dt><dd>{template.active ? 'Active' : 'Inactive'}</dd></div></> : null}</dl><div className="template-card__actions">{profiles.data?.length ? <button className="button" onClick={() => setComparisonTargetKey(`template:${latest.id}`)}><GitCompareArrows size={16} /> Compare settings</button> : null}<a className="button" href={`/api/v1/profiles/templates/${template.id}/exports/json`} aria-label={`Export ${template.name}`}><Download size={16} /> Export JSON</a>{user?.role !== 'viewer' ? <><button className="button" disabled={openingTemplateId === template.id} onClick={() => { void openEditor(template) }}><Pencil size={16} /> {openingTemplateId === template.id ? 'Refreshing…' : 'Edit template'}</button><button className="button button--danger" onClick={() => { deleteTemplate.reset(); setDeleteConfirmation(''); setDeleteTarget(template) }}><Trash2 size={16} /> Delete</button></> : null}</div></article>
    })}</section>}
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
    {showImport ? <Modal title="Import material template" description="Use a template JSON exported by Filament Manager. Create a scoped template or explicitly replace the settings of an existing template." onClose={() => setShowImport(false)} footer={<><button type="button" className="button" onClick={() => setShowImport(false)}>Cancel</button><button type="button" className="button button--primary" disabled={!importDocument || importTemplate.isPending || (importMode === 'overwrite' && (!importTargetId || !confirmOverwrite)) || (importMode === 'create' && (!importPrinterId || !importNozzleId || !importMaterialType.trim()))} onClick={() => importTemplate.mutate()}><FileUp size={17} />{importTemplate.isPending ? 'Importing…' : importMode === 'overwrite' ? 'Overwrite template' : 'Create template'}</button></>}>
      <div className="editor-form">
        <label>Template JSON file<input type="file" accept="application/json,.json" onChange={(event) => { void readImportFile(event.target.files?.[0]) }} autoFocus /></label>
        {importFileError ? <p className="form-error" role="alert">{importFileError}</p> : null}
        {importDocument ? <div className="deployment-note"><strong>{importDocument.template.name}</strong><span>{importDocument.template.material_type} · {compactNumber(importDocument.template.filament_diameter_mm, 2)} mm filament</span></div> : null}
        <fieldset><legend>Import action</legend><label className="choice-row"><input type="radio" name="template_import_mode" checked={importMode === 'create'} onChange={() => { setImportMode('create'); setConfirmOverwrite(false) }} /> Create a new scoped template</label><label className="choice-row"><input type="radio" name="template_import_mode" checked={importMode === 'overwrite'} onChange={() => setImportMode('overwrite')} /> Overwrite an existing template’s settings</label></fieldset>
        {importMode === 'create' ? <div className="form-grid"><label>Material type<input value={importMaterialType} onChange={(event) => setImportMaterialType(event.target.value)} list="import-material-types" maxLength={48} required /><datalist id="import-material-types">{['PLA', 'PLA+', 'PETG', 'ASA', 'ABS', 'TPU', 'PEBA', 'PP', 'PCTPE', 'Nylon 645'].map((material) => <option key={material} value={material} />)}</datalist></label><label>Printer<select value={importPrinterId} onChange={(event) => setImportPrinterId(event.target.value)} required>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label><label>Physical nozzle<select value={importNozzleId} onChange={(event) => setImportNozzleId(event.target.value)} required><option value="" disabled>No nozzle available</option>{nozzles.data?.filter((nozzle) => nozzle.printer_id === importPrinterId).map((nozzle) => <option key={nozzle.id} value={nozzle.id}>{nozzle.nozzle_code} · {compactNumber(nozzle.diameter_mm, 1)} mm · {nozzle.material}</option>)}</select></label></div> : <div className="editor-form"><label>Existing template<select value={importTargetId} onChange={(event) => { setImportTargetId(event.target.value); setConfirmOverwrite(false) }} required>{templates.data?.filter((template) => template.active).map((template) => <option key={template.id} value={template.id}>{template.name} · {printers.data?.find((printer) => printer.id === template.printer_id)?.name ?? 'Unknown printer'} · {compactNumber(template.nozzle_diameter_mm, 1)} mm</option>)}</select></label><p className="warning-note">Only the selected template’s settings are replaced. Its identity, printer, and nozzle stay unchanged. Linked filament profiles inherit the imported values and Cura synchronization is queued.</p><label className="choice-row"><input type="checkbox" checked={confirmOverwrite} onChange={(event) => setConfirmOverwrite(event.target.checked)} /> I confirm that I want to overwrite the selected template settings.</label></div>}
        {importTemplate.error ? <FormSubmissionError error={importTemplate.error} /> : null}
      </div>
    </Modal> : null}
    {showEditor ? <Modal title={editSource ? `Edit ${editSource.name}` : 'Add material template'} description={editSource ? 'Save current settings directly. Linked profiles inherit the change immediately unless a value is customized.' : 'Group the template identity and all Cura settings in one guided editor.'} onClose={closeEditor} size="wide" footer={<><button type="button" className="button" onClick={closeEditor}>Cancel</button><button type="submit" className="button button--primary" form="edit-material-template" disabled={save.isPending}>{editSource ? <Pencil size={17} /> : <Plus size={17} />}{save.isPending ? 'Saving…' : 'Save template'}</button></>}>
      <form ref={editorFormRef} id="edit-material-template" className="editor-form" onSubmit={submit} onInvalid={centerNativeInvalid} key={editSource?.revisions[0]?.id ?? 'new-template'}>
        <EditorSection title="Template identity" description="Scope the reusable starting point to a printer, physical nozzle, and filament diameter. Linked profiles move with a changed scope when no conflicting profile exists.">
          <div className="form-grid">
            <label>Material type<input name="material_type" list="common-material-types" placeholder="PLA, PEBA, PP…" defaultValue={editSource?.material_type ?? ''} required autoFocus aria-invalid={identityError('material_type').length ? true : undefined} aria-describedby={identityError('material_type').length ? identityErrorId('material_type') : undefined} /><small className="field-help">Cura name: Template + material type; brand: Template.</small>{identityFieldError('material_type')}<datalist id="common-material-types">{['PLA', 'PLA+', 'PETG', 'ASA', 'ABS', 'TPU', 'PEBA', 'PP', 'PCTPE', 'Nylon 645'].map((material) => <option key={material} value={material} />)}</datalist></label>
            <label>Printer<select name="printer_id" value={newPrinterId} onChange={(event) => setNewPrinterId(event.target.value)} required aria-invalid={identityError('printer_id').length ? true : undefined} aria-describedby={identityError('printer_id').length ? identityErrorId('printer_id') : undefined}>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select>{identityFieldError('printer_id')}</label>
            <label>Physical nozzle<select name="nozzle_id" value={newNozzleId} onChange={(event) => setNewNozzleId(event.target.value)} required aria-invalid={identityError('nozzle_id').length ? true : undefined} aria-describedby={identityError('nozzle_id').length ? identityErrorId('nozzle_id') : undefined}><option value="" disabled>No nozzle available</option>{nozzles.data?.filter((nozzle) => nozzle.printer_id === newPrinterId).map((nozzle) => <option key={nozzle.id} value={nozzle.id}>{nozzle.nozzle_code} · {compactNumber(nozzle.diameter_mm, 1)} mm · {nozzle.material}</option>)}</select>{identityFieldError('nozzle_id')}</label>
            <label>Filament diameter<input name="filament_diameter_mm" type="number" min="0.1" step="0.01" defaultValue={editSource?.filament_diameter_mm ?? '1.75'} required aria-invalid={identityError('filament_diameter_mm').length ? true : undefined} aria-describedby={identityError('filament_diameter_mm').length ? identityErrorId('filament_diameter_mm') : undefined} />{identityFieldError('filament_diameter_mm')}</label>
            <label className="form-grid__wide">Description<textarea name="description" rows={2} defaultValue={editSource?.description ?? ''} placeholder="Purpose, behavior, and calibration notes" aria-invalid={identityError('description').length ? true : undefined} aria-describedby={identityError('description').length ? identityErrorId('description') : undefined} />{identityFieldError('description')}</label>
          </div>
        </EditorSection>
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
    {deleteTarget ? <Modal title={`Delete ${deleteTarget.name}?`} description="This is a destructive catalog action. The template will be removed from active choices and from the managed Cura library." onClose={() => setDeleteTarget(null)} footer={<><button type="button" className="button" onClick={() => setDeleteTarget(null)}>Cancel</button><button type="button" className="button button--danger" disabled={deleteConfirmation !== deleteTarget.name || deleteTemplate.isPending} onClick={() => deleteTemplate.mutate(deleteTarget)}><Trash2 size={17} /> {deleteTemplate.isPending ? 'Deleting…' : 'Delete template'}</button></>}>
      <div className="editor-form">
        <p className="form-error"><AlertTriangle size={17} /> Existing filament and print-history snapshots are preserved for recovery and audit, but this template will no longer be editable or synchronized to Cura.</p>
        <label>Type <strong>{deleteTarget.name}</strong> to confirm<input value={deleteConfirmation} onChange={(event) => setDeleteConfirmation(event.target.value)} autoComplete="off" autoFocus /></label>
        {deleteTemplate.error ? <FormSubmissionError error={deleteTemplate.error} /> : null}
      </div>
    </Modal> : null}
  </div>
}
