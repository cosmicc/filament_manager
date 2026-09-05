import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Copy, Download, GitCompareArrows, Pencil, Plus, Save, Trash2 } from 'lucide-react'
import { type InvalidEvent, useEffect, useMemo, useRef, useState } from 'react'
import { actionableApiError, apiFetch, validationMessagesFor } from '../api/client'
import type { BuildPlate, CuraSettingCatalogItem, Filament, FilamentColor, MaterialProfile, MaterialTemplate, Printer } from '../api/types'
import { InventoryChoiceSelect } from '../components/NewItemSelect'
import { DryingTemperatureDetails } from '../components/DryingTemperatureDetails'
import { ChangeFilamentTemplateModal } from '../components/ChangeFilamentTemplateModal'
import { EditorSection } from '../components/EditorSection'
import { FormSubmissionError } from '../components/FormSubmissionError'
import { EmptyState } from '../components/EmptyState'
import { FilamentColorEditor, type FilamentColorMode } from '../components/FilamentColorEditor'
import { LoadingState } from '../components/LoadingState'
import { MaterialComparisonModal } from '../components/MaterialComparisonModal'
import { materialSettingLabel, MaterialSettingsEditor, settingsFromForm } from '../components/MaterialSettingsEditor'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../context/AuthContext'
import { Link, useRouter } from '../context/RouterContext'
import { filamentSwatchStyle } from '../lib/colors'
import { compactNumber, inputNumber } from '../lib/format'
import { materialIdentitySummary, materialModifierSummary } from '../lib/materialIdentity'

function optional(data: FormData, key: string) {
  const value = String(data.get(key) ?? '').trim()
  return value || null
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

const productFieldLabels: Record<string, string> = {
  vendor_id: 'Manufacturer',
  material_type: 'Material type',
  color_name: 'Color name',
  color_mode: 'Display type',
  color_hex: 'Screen color sample',
  color_hexes: 'Color samples',
  diameter_mm: 'Filament diameter',
  tolerance_mm: 'Diameter tolerance',
  density_g_cm3: 'Density',
  nominal_net_mass_g: 'Nominal net mass',
  filler: 'Filler',
  finish: 'Finish',
  notes: 'Notes',
}

export default function FilamentDetailPage() {
  const { path, navigate } = useRouter()
  const { user } = useAuth()
  const client = useQueryClient()
  const filamentId = path.split('/')[2] ?? ''
  const filament = useQuery({ queryKey: ['filament', filamentId], queryFn: () => apiFetch<Filament>(`/filaments/${filamentId}`), enabled: Boolean(filamentId) })
  const colors = useQuery({ queryKey: ['filament-colors'], queryFn: () => apiFetch<FilamentColor[]>('/filament-colors') })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=false') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const catalog = useQuery({ queryKey: ['cura-settings-catalog'], queryFn: () => apiFetch<CuraSettingCatalogItem[]>('/profiles/cura-settings/catalog') })
  const [colorName, setColorName] = useState('')
  const [colorMode, setColorMode] = useState<FilamentColorMode>('solid')
  const [colorHexes, setColorHexes] = useState(['808080'])
  const [materialType, setMaterialType] = useState('')
  const [editingProduct, setEditingProduct] = useState(false)
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null)
  const [changingTemplate, setChangingTemplate] = useState<MaterialProfile | null>(null)
  const [comparisonProfileId, setComparisonProfileId] = useState<string | null>(null)
  const [addingSettings, setAddingSettings] = useState(false)
  const [addTemplateRevisionId, setAddTemplateRevisionId] = useState('')
  const [message, setMessage] = useState('')
  const productFormRef = useRef<HTMLFormElement>(null)
  const nativeInvalidPending = useRef(false)

  useEffect(() => {
    if (!filament.data) return
    setColorName(filament.data.color_name)
    setColorMode(filament.data.color_mode)
    setColorHexes(filament.data.color_hexes.length ? filament.data.color_hexes : [filament.data.color_hex ?? '808080'])
    setMaterialType(filament.data.material_type)
  }, [filament.data])

  const printerName = (printerId: string) => printers.data?.find((printer) => printer.id === printerId)?.name ?? printerId
  const currentProfiles = useMemo(
    () => (profiles.data ?? [])
      .filter((profile) => profile.filament_product_id === filamentId)
      .sort((left, right) => printerName(left.printer_id).localeCompare(printerName(right.printer_id))
        || left.printer_id.localeCompare(right.printer_id)
        || Number(left.nozzle_diameter_mm) - Number(right.nozzle_diameter_mm)
        || left.id.localeCompare(right.id)),
    // Printer metadata changes the operator-facing deterministic ordering.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filamentId, printers.data, profiles.data],
  )
  const editingProfile = currentProfiles.find((profile) => profile.id === editingProfileId) ?? null
  const canEdit = user?.role !== 'viewer'

  const update = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      if (!filament.data) throw new Error('Filament is unavailable')
      const data = new FormData(form)
      return apiFetch<Filament>(`/filaments/${filamentId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          expected_version: filament.data.record_version,
          vendor_id: optional(data, 'vendor_id'),
          material_type: materialType.trim(),
          color_name: colorName.trim(),
          color_hex: colorHexes[0],
          color_mode: colorMode,
          // Do not send Rainbow's fixed six-sample response palette through
          // the one-to-three user-defined multicolor request contract.
          color_hexes: colorMode === 'rainbow' ? [] : colorHexes,
          diameter_mm: String(data.get('diameter_mm')),
          tolerance_mm: optional(data, 'tolerance_mm'),
          density_g_cm3: String(data.get('density_g_cm3')),
          nominal_net_mass_g: String(data.get('nominal_net_mass_g')),
          filler: optional(data, 'filler'),
          finish: optional(data, 'finish'),
          notes: optional(data, 'notes'),
        }),
      })
    },
    onSuccess: async () => {
      setMessage('Filament details saved. Density changes were applied to every current print-settings scope.')
      setEditingProduct(false)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['filament', filamentId] }),
        client.invalidateQueries({ queryKey: ['filaments'] }),
        client.invalidateQueries({ queryKey: ['profiles'] }),
        client.invalidateQueries({ queryKey: ['filament-colors'] }),
        client.invalidateQueries({ queryKey: ['spools'] }),
      ])
    },
  })
  const remove = useMutation({
    mutationFn: () => apiFetch<{ disposition: string }>(`/filaments/${filamentId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['filaments'] }),
        client.invalidateQueries({ queryKey: ['profiles'] }),
        client.invalidateQueries({ queryKey: ['spools'] }),
      ])
      navigate('/filaments')
    },
    onError: (error: Error) => setMessage(actionableApiError(error)),
  })
  const saveProfile = useMutation({
    mutationFn: ({ profile, form }: { profile: MaterialProfile; form: HTMLFormElement }) => apiFetch<MaterialProfile>(`/profiles/${profile.id}/settings`, {
      method: 'PUT',
      body: JSON.stringify({ expected_profile_version: profile.record_version, settings: settingsFromForm(form, catalog.data ?? [], 'profile') }),
    }),
    onSuccess: async () => {
      setMessage('Print settings saved for the selected printer and nozzle. Cura synchronization was queued automatically.')
      setEditingProfileId(null)
      await client.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const addProfile = useMutation({
    mutationFn: (revisionId: string) => apiFetch<MaterialProfile>('/profiles/from-template', {
      method: 'POST',
      body: JSON.stringify({ filament_product_id: filamentId, material_template_revision_id: revisionId }),
    }),
    onSuccess: async () => {
      setAddingSettings(false)
      setAddTemplateRevisionId('')
      setMessage('A new printer/nozzle print-settings scope was created and queued for Cura synchronization.')
      await client.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const profileValidationErrors = validationMessagesFor(saveProfile.error, 'settings')
  const productValidationErrors = useMemo(() => validationMessagesFor(update.error), [update.error])
  const productErrorsFor = (field: string) => productValidationErrors[field] ?? []
  const productErrorId = (field: string) => `filament-product-${field}-error`
  const productFieldError = (field: string) => productErrorsFor(field).length ? (
    <span className="field-validation" id={productErrorId(field)} role="alert">
      {productErrorsFor(field).map((error) => <span key={error}>{error}</span>)}
    </span>
  ) : null

  useEffect(() => {
    if (!update.error || !Object.keys(productValidationErrors).length) return undefined
    const frame = window.requestAnimationFrame(() => {
      const control = productFormRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')
      if (control) centerAndFocus(control)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [productValidationErrors, update.error])

  if (filament.isLoading) return <LoadingState label="Loading filament details" />
  if (!filament.data) return <div><Link className="button" to="/filaments"><ArrowLeft size={16} /> Filaments</Link><p className="form-error">{filament.error?.message ?? 'Filament not found'}</p></div>
  const item = filament.data
  const itemModifiers = materialModifierSummary(item)
  const occupiedScopes = new Set(currentProfiles.map((profile) => `${profile.printer_id}:${Number(profile.nozzle_diameter_mm)}`))
  const availableTemplateOptions = (templates.data ?? []).flatMap((template) => {
    const revision = template.revisions[0]
    if (!revision || template.material_type.toLowerCase() !== item.material_type.toLowerCase()) return []
    if (occupiedScopes.has(`${template.printer_id}:${Number(template.nozzle_diameter_mm)}`)) return []
    return [{ template, revision }]
  }).sort((left, right) => printerName(left.template.printer_id).localeCompare(printerName(right.template.printer_id))
    || Number(left.template.nozzle_diameter_mm) - Number(right.template.nozzle_diameter_mm)
    || left.template.name.localeCompare(right.template.name))
  const closeProductEditor = () => {
    setColorName(item.color_name)
    setColorMode(item.color_mode)
    setColorHexes(item.color_hexes.length ? item.color_hexes : [item.color_hex ?? '808080'])
    setMaterialType(item.material_type)
    setEditingProduct(false)
    update.reset()
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
    <PageHeader eyebrow={item.vendor_name ?? 'Unspecified manufacturer'} title={materialIdentitySummary(item)} description="Manage the physical filament identity separately from its printer/nozzle-specific print settings." actions={<><Link className="button" to="/filaments"><ArrowLeft size={16} /> All filaments</Link>{canEdit ? <><Link className="button" to={`/filaments/duplicate/${item.id}`}><Copy size={16} /> Duplicate</Link>{!item.archived ? <Link className="button button--primary" to={`/spools?create=1&filament_id=${encodeURIComponent(item.id)}`}><Plus size={16} /> Create spool from filament</Link> : null}</> : null}</>} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    <section className="card product-editor">
      <header className="card__header"><div><p className="eyebrow">Canonical filament</p><h2>Product details</h2></div><div className="card-header-actions"><span className="filament-swatch" style={filamentSwatchStyle(item.color_mode, item.color_hexes, item.color_hex ?? '808080')} />{canEdit ? <><button className="button" onClick={() => { update.reset(); setEditingProduct(true) }}><Pencil size={16} /> Edit product</button><button className="button button--danger" disabled={remove.isPending} onClick={() => { if (window.confirm('Delete this filament? It will be archived instead if retained history prevents safe deletion.')) remove.mutate() }}><Trash2 size={16} /> {remove.isPending ? 'Removing…' : 'Delete or archive'}</button></> : null}</div></header>
      <dl className="definition-list"><div><dt>Manufacturer</dt><dd>{item.vendor_name ?? 'Unspecified manufacturer'}</dd></div><div><dt>Material</dt><dd>{item.material_type}{itemModifiers ? ` · ${itemModifiers}` : ''}</dd></div><div><dt>Color</dt><dd>{item.color_name} · {item.color_mode === 'rainbow' ? 'Rainbow' : item.color_hexes.map((color) => `#${color}`).join(' / ')}</dd></div><div><dt>Diameter</dt><dd>{compactNumber(item.diameter_mm, 2)} mm{item.tolerance_mm ? ` ± ${compactNumber(item.tolerance_mm, 2)} mm` : ''}</dd></div><div><dt>Density</dt><dd>{compactNumber(item.density_g_cm3, 2)} g/cm³</dd></div><div><dt>Nominal net mass</dt><dd>{compactNumber(item.nominal_net_mass_g, 0)} g</dd></div><div><dt>Notes</dt><dd>{item.notes ?? 'No notes'}</dd></div></dl>
      <dl className="definition-list"><DryingTemperatureDetails filamentId={item.id} /></dl>
    </section>

    <section className="profile-scope-section" aria-labelledby="filament-print-settings-heading">
      <header className="section-heading"><div><p className="eyebrow">Slicer-ready configurations</p><h2 id="filament-print-settings-heading">Print settings</h2><p>Each card is one independent printer and nozzle scope with its own linked template and explicit customizations.</p></div>{canEdit ? <button className="button button--primary" disabled={!availableTemplateOptions.length} title={availableTemplateOptions.length ? undefined : 'Every compatible template scope is already configured'} onClick={() => { setAddTemplateRevisionId(availableTemplateOptions[0]?.revision.id ?? ''); setAddingSettings(true) }}><Plus size={16} /> Add print settings</button> : null}</header>
      {!currentProfiles.length ? <EmptyState icon={Plus} title="No print settings" description="Add a compatible material template scope for this filament." /> : <div className="profile-scope-grid">{currentProfiles.map((profile) => <article className="card profile-scope-card" key={profile.id}>
        <header><div><p className="eyebrow">{printerName(profile.printer_id)}</p><h3>{compactNumber(profile.nozzle_diameter_mm, 1)} mm nozzle</h3></div><span className={profile.override_count ? 'profile-ownership profile-ownership--customized' : 'profile-ownership'}>{profile.override_count ? `${profile.override_count} customized` : 'Inherited'}</span></header>
        <dl className="definition-list definition-list--compact"><div><dt>Linked template</dt><dd>{profile.base_template_name ?? 'Missing template'}</dd></div><div><dt>Printing temperature</dt><dd>{compactNumber(profile.extruder_temp_c, 0)} °C</dd></div><div><dt>Initial layer build plate temperature</dt><dd>{compactNumber(profile.initial_bed_temp_c, 0)} °C</dd></div><div><dt>Build plate temperature</dt><dd>{compactNumber(profile.bed_temp_c, 0)} °C</dd></div><div><dt>Build volume temperature</dt><dd>{profile.chamber_temp_c == null ? 'Not set' : `${compactNumber(profile.chamber_temp_c, 0)} °C`}</dd></div><div><dt>Resolved Cura settings</dt><dd>{Object.keys(profile.cura_settings).length}</dd></div><div><dt>Profile version</dt><dd>{profile.version}</dd></div></dl>
        <footer className="profile-scope-actions">{canEdit ? <><button className="button" onClick={() => { saveProfile.reset(); setEditingProfileId(profile.id) }}><Pencil size={16} /> Edit settings</button><button className="button" onClick={() => setChangingTemplate(profile)}>Change template</button></> : null}<button className="button" onClick={() => setComparisonProfileId(profile.id)}><GitCompareArrows size={16} /> Compare</button><a className="button" href={`/api/v1/profiles/${profile.id}/exports/cura`}><Download size={16} /> Export Cura JSON</a></footer>
      </article>)}</div>}
    </section>
    {changingTemplate ? <ChangeFilamentTemplateModal filament={item} profile={changingTemplate} templates={templates.data ?? []} onClose={() => setChangingTemplate(null)} /> : null}

    {editingProduct ? <Modal title="Edit filament product" description="Update the canonical product identity and physical specifications. Print-setting templates are managed per printer/nozzle card." onClose={closeProductEditor} size="wide" footer={<><button className="button" type="button" onClick={closeProductEditor}>Cancel</button><button className="button button--primary" form="edit-filament-product" disabled={update.isPending}><Save size={17} />{update.isPending ? 'Saving…' : 'Save filament'}</button></>}>
      <form ref={productFormRef} id="edit-filament-product" className="editor-form" onSubmit={(event) => { event.preventDefault(); setMessage(''); update.mutate(event.currentTarget) }} onInvalid={centerNativeInvalid}>
        <EditorSection title="Product identity" description="Names and the shared screen color sample used throughout the application.">
          <div className="form-grid">
            <label>Manufacturer<InventoryChoiceSelect kind="manufacturer" name="vendor_id" defaultValue={item.vendor_id ?? ''} autoFocus aria-invalid={productErrorsFor('vendor_id').length ? true : undefined} aria-describedby={productErrorsFor('vendor_id').length ? productErrorId('vendor_id') : undefined} />{productFieldError('vendor_id')}</label>
            <label>Material type<input name="material_type" value={materialType} onChange={(event) => setMaterialType(event.target.value)} maxLength={48} required aria-invalid={productErrorsFor('material_type').length ? true : undefined} aria-describedby={productErrorsFor('material_type').length ? productErrorId('material_type') : undefined} />{productFieldError('material_type')}</label>
            <FilamentColorEditor name={colorName} mode={colorMode} colorHexes={colorHexes} rememberedColors={colors.data ?? []} onNameChange={setColorName} onModeChange={setColorMode} onColorsChange={setColorHexes} validationErrors={productValidationErrors} errorIdPrefix="filament-product-color" disabled={!item.color_editable} />
            {!item.color_editable ? <p className="security-note form-grid__wide">Color is locked because this filament already has recorded spool use or print history.</p> : null}
          </div>
        </EditorSection>
        <EditorSection title="Physical specifications" description="Dimensions, density, packaged mass, and material modifiers.">
          <div className="form-grid">
            <label>Filament diameter (mm)<input name="diameter_mm" type="number" min="0.1" step="0.01" defaultValue={inputNumber(item.diameter_mm, 2)} required aria-invalid={productErrorsFor('diameter_mm').length ? true : undefined} aria-describedby={productErrorsFor('diameter_mm').length ? productErrorId('diameter_mm') : undefined} />{productFieldError('diameter_mm')}</label>
            <label>Diameter tolerance (mm)<input name="tolerance_mm" type="number" min="0" step="0.01" defaultValue={inputNumber(item.tolerance_mm, 2)} aria-invalid={productErrorsFor('tolerance_mm').length ? true : undefined} aria-describedby={productErrorsFor('tolerance_mm').length ? productErrorId('tolerance_mm') : undefined} />{productFieldError('tolerance_mm')}</label>
            <label>Density (g/cm³)<input name="density_g_cm3" type="number" min="0.01" step="0.01" defaultValue={inputNumber(item.density_g_cm3, 2)} required aria-invalid={productErrorsFor('density_g_cm3').length ? true : undefined} aria-describedby={productErrorsFor('density_g_cm3').length ? productErrorId('density_g_cm3') : undefined} />{productFieldError('density_g_cm3')}</label>
            <label>Nominal net mass (g)<input name="nominal_net_mass_g" type="number" min="1" step="1" defaultValue={inputNumber(item.nominal_net_mass_g, 0)} required aria-invalid={productErrorsFor('nominal_net_mass_g').length ? true : undefined} aria-describedby={productErrorsFor('nominal_net_mass_g').length ? productErrorId('nominal_net_mass_g') : undefined} />{productFieldError('nominal_net_mass_g')}</label>
            <label>Filler<InventoryChoiceSelect kind="filler" name="filler" defaultValue={item.filler ?? 'None'} aria-invalid={productErrorsFor('filler').length ? true : undefined} aria-describedby={productErrorsFor('filler').length ? productErrorId('filler') : undefined} />{productFieldError('filler')}</label>
            <label>Finish<InventoryChoiceSelect kind="finish" name="finish" defaultValue={item.finish ?? 'Standard'} aria-invalid={productErrorsFor('finish').length ? true : undefined} aria-describedby={productErrorsFor('finish').length ? productErrorId('finish') : undefined} />{productFieldError('finish')}</label>
            <label className="form-grid__wide">Notes<textarea name="notes" defaultValue={item.notes ?? ''} maxLength={4000} rows={3} aria-invalid={productErrorsFor('notes').length ? true : undefined} aria-describedby={productErrorsFor('notes').length ? productErrorId('notes') : undefined} />{productFieldError('notes')}</label>
          </div>
        </EditorSection>
        <FormSubmissionError error={update.error} fieldLabel={(field) => productFieldLabels[field] ?? field.replaceAll('_', ' ')} conflictMessage="This filament changed after the editor opened. Close the editor, review the latest values, and try again." />
      </form>
    </Modal> : null}
    {editingProfile ? <Modal title={`Edit ${printerName(editingProfile.printer_id)} · ${compactNumber(editingProfile.nozzle_diameter_mm, 1)} mm settings`} description={`Edit values inherited from ${editingProfile.base_template_name ?? 'the linked template'}. Only explicit differences are stored as filament customizations.`} onClose={() => setEditingProfileId(null)} size="wide" footer={<><button className="button" type="button" onClick={() => setEditingProfileId(null)}>Cancel</button><button className="button button--primary" form="edit-material-profile" disabled={saveProfile.isPending}><Save size={16} />{saveProfile.isPending ? 'Saving…' : 'Save settings'}</button></>}><form id="edit-material-profile" className="editor-form" onSubmit={(event) => { event.preventDefault(); saveProfile.mutate({ profile: editingProfile, form: event.currentTarget }) }} key={editingProfile.id}><MaterialSettingsEditor settings={editingProfile} baseSettings={editingProfile.base_template_settings} overrideKeys={editingProfile.override_keys} validationErrors={profileValidationErrors} catalog={catalog.data ?? []} plates={plates.data ?? []} scope="profile" /><FormSubmissionError error={saveProfile.error} fieldLabel={(field) => materialSettingLabel(field, catalog.data ?? [])} /></form></Modal> : null}
    {addingSettings ? <Modal title="Add print settings" description="Choose one active material template for a printer/nozzle scope this filament does not already have." onClose={() => setAddingSettings(false)} footer={<><button className="button" type="button" onClick={() => setAddingSettings(false)}>Cancel</button><button className="button button--primary" disabled={addProfile.isPending || !addTemplateRevisionId} onClick={() => addProfile.mutate(addTemplateRevisionId)}><Plus size={16} />{addProfile.isPending ? 'Adding…' : 'Add settings'}</button></>}><EditorSection title="Compatible template" description="The filament density is applied automatically while all other values begin from this template."><label>Printer and nozzle<select value={addTemplateRevisionId} onChange={(event) => setAddTemplateRevisionId(event.target.value)} autoFocus>{availableTemplateOptions.map(({ template, revision }) => <option key={revision.id} value={revision.id}>{template.name} · {printerName(template.printer_id)} · {compactNumber(template.nozzle_diameter_mm, 1)} mm</option>)}</select></label></EditorSection>{addProfile.error ? <p className="form-error" role="alert">{addProfile.error.message}</p> : null}</Modal> : null}
    {comparisonProfileId ? <MaterialComparisonModal profiles={profiles.data ?? []} templates={templates.data ?? []} printers={printers.data ?? []} filaments={[item]} plates={plates.data ?? []} catalog={catalog.data ?? []} initialProfileId={comparisonProfileId} onClose={() => setComparisonProfileId(null)} /> : null}
  </div>
}
