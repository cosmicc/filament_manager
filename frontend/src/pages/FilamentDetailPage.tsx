import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Copy, Pencil, Save, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { apiFetch, validationMessagesFor } from '../api/client'
import type {
  BuildPlate,
  CuraSettingCatalogItem,
  Filament,
  FilamentColor,
  MaterialProfile,
  MaterialTemplate,
  Printer,
  Vendor,
} from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { FilamentColorEditor, type FilamentColorMode } from '../components/FilamentColorEditor'
import { LoadingState } from '../components/LoadingState'
import { MaterialSettingsEditor, settingsFromForm } from '../components/MaterialSettingsEditor'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../context/AuthContext'
import { Link, useRouter } from '../context/RouterContext'
import { filamentSwatchStyle } from '../lib/colors'
import { compactNumber, inputNumber } from '../lib/format'

function optional(data: FormData, key: string) {
  const value = String(data.get(key) ?? '').trim()
  return value || null
}

export default function FilamentDetailPage() {
  const { path, navigate } = useRouter()
  const { user } = useAuth()
  const client = useQueryClient()
  const filamentId = path.split('/')[2] ?? ''
  const filament = useQuery({
    queryKey: ['filament', filamentId],
    queryFn: () => apiFetch<Filament>(`/filaments/${filamentId}`),
    enabled: Boolean(filamentId),
  })
  const colors = useQuery({ queryKey: ['filament-colors'], queryFn: () => apiFetch<FilamentColor[]>('/filament-colors') })
  const vendors = useQuery({ queryKey: ['vendors'], queryFn: () => apiFetch<Vendor[]>('/vendors') })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=false') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const catalog = useQuery({ queryKey: ['cura-settings-catalog'], queryFn: () => apiFetch<CuraSettingCatalogItem[]>('/profiles/cura-settings/catalog') })
  const [colorName, setColorName] = useState('')
  const [colorMode, setColorMode] = useState<FilamentColorMode>('solid')
  const [colorHexes, setColorHexes] = useState(['808080'])
  const [materialType, setMaterialType] = useState('')
  const [templateRevisionId, setTemplateRevisionId] = useState('')
  const [editingProduct, setEditingProduct] = useState(false)
  const [editingSettings, setEditingSettings] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!filament.data) return
    setColorName(filament.data.color_name)
    setColorMode(filament.data.color_mode)
    setColorHexes(filament.data.color_hexes.length ? filament.data.color_hexes : [filament.data.color_hex ?? '808080'])
    setMaterialType(filament.data.material_type)
  }, [filament.data])

  const productProfiles = useMemo(
    () => (profiles.data ?? [])
      .filter((profile) => profile.filament_product_id === filamentId)
      .sort((left, right) => right.version - left.version),
    [filamentId, profiles.data],
  )
  const latestProfile = productProfiles[0]
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
          product_name: optional(data, 'product_name'),
          material_type: materialType.trim(),
          color_name: colorName.trim(),
          color_hex: colorHexes[0],
          color_mode: colorMode,
          color_hexes: colorHexes,
          diameter_mm: String(data.get('diameter_mm')),
          tolerance_mm: optional(data, 'tolerance_mm'),
          density_g_cm3: String(data.get('density_g_cm3')),
          nominal_net_mass_g: String(data.get('nominal_net_mass_g')),
          filler: optional(data, 'filler'),
          finish: optional(data, 'finish'),
          notes: optional(data, 'notes'),
          material_template_revision_id: templateRevisionId || currentTemplateRevisionId,
        }),
      })
    },
    onSuccess: async () => {
      setMessage('Filament details saved. The selected sample now applies to every matching color name.')
      setEditingProduct(false)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['filament', filamentId] }),
        client.invalidateQueries({ queryKey: ['filaments'] }),
        client.invalidateQueries({ queryKey: ['filament-colors'] }),
        client.invalidateQueries({ queryKey: ['spools'] }),
      ])
    },
    onError: (error: Error) => setMessage(error.message),
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
    onError: (error: Error) => setMessage(error.message),
  })
  const saveProfile = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      if (!latestProfile) throw new Error('This filament does not have a starting profile')
      return apiFetch<MaterialProfile>(`/profiles/${latestProfile.id}/settings`, {
        method: 'PUT',
        body: JSON.stringify({
          expected_profile_version: latestProfile.record_version,
          settings: settingsFromForm(form, catalog.data ?? []),
        }),
      })
    },
    onSuccess: async () => {
      setMessage('Profile settings saved. Customized values remain independent; all other values continue to inherit from the linked template. Cura synchronization was queued automatically.')
      setEditingSettings(false)
      await client.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const profileValidationErrors = validationMessagesFor(saveProfile.error, 'settings')
  const hasProfileValidationErrors = Object.keys(profileValidationErrors).length > 0

  if (filament.isLoading) return <LoadingState label="Loading filament details" />
  if (!filament.data) return <div><Link className="button" to="/filaments"><ArrowLeft size={16} /> Filaments</Link><p className="form-error">{filament.error?.message ?? 'Filament not found'}</p></div>
  const item = filament.data
  const compatibleTemplateOptions = (templates.data ?? []).flatMap((template) => {
    const revision = template.revisions[0]
    if (!revision || template.material_type.toLocaleLowerCase() !== materialType.trim().toLocaleLowerCase()) {
      return []
    }
    if (latestProfile && (
      template.printer_id !== latestProfile.printer_id
      || Number(template.nozzle_diameter_mm) !== Number(latestProfile.nozzle_diameter_mm)
    )) {
      return []
    }
    return [{ template, revision }]
  }).sort((left, right) => {
    const leftCurrent = left.template.id === latestProfile?.base_template_id ? 0 : 1
    const rightCurrent = right.template.id === latestProfile?.base_template_id ? 0 : 1
    return leftCurrent - rightCurrent || left.template.name.localeCompare(right.template.name)
  })
  const currentTemplateRevisionId = compatibleTemplateOptions.find(
    ({ template }) => template.id === latestProfile?.base_template_id,
  )?.revision.id ?? item.material_template_revision_id ?? ''
  const closeProductEditor = () => {
    setColorName(item.color_name)
    setColorMode(item.color_mode)
    setColorHexes(item.color_hexes.length ? item.color_hexes : [item.color_hex ?? '808080'])
    setMaterialType(item.material_type)
    setTemplateRevisionId(currentTemplateRevisionId)
    setEditingProduct(false)
  }

  return <div>
    <PageHeader
      eyebrow={`${item.vendor_name ?? 'Unspecified vendor'} · ${item.material_type}`}
      title={item.product_name ?? `${item.material_type} ${item.color_name}`}
      description="Edit canonical product details and every Cura material setting stored for this filament."
      actions={<><Link className="button" to="/filaments"><ArrowLeft size={16} /> All filaments</Link>{canEdit ? <Link className="button button--primary" to={`/filaments/duplicate/${item.id}`}><Copy size={16} /> Duplicate</Link> : null}</>}
    />
    {message && <div className="deployment-note" role="status">{message}</div>}
    <div className="detail-grid">
      <section className="card product-editor">
        <header className="card__header"><div><p className="eyebrow">Canonical filament</p><h2>Product details</h2></div><div className="card-header-actions"><span className="filament-swatch" style={filamentSwatchStyle(item.color_mode, item.color_hexes, item.color_hex ?? '808080')} />{canEdit ? <><button className="button" onClick={() => { setTemplateRevisionId(currentTemplateRevisionId); setEditingProduct(true) }}><Pencil size={16} /> Edit</button><button className="button button--danger" disabled={remove.isPending} onClick={() => { if (window.confirm('Delete this filament? It will be archived instead if retained history prevents safe deletion.')) remove.mutate() }}><Trash2 size={16} /> {remove.isPending ? 'Removing…' : 'Delete or archive'}</button></> : null}</div></header>
        <dl className="definition-list">
          <div><dt>Vendor and product</dt><dd>{item.vendor_name ?? 'Unspecified vendor'} · {item.product_name ?? 'No product name'}</dd></div>
          <div><dt>Material</dt><dd>{item.material_type}{item.filler ? ` · ${item.filler}` : ''}{item.finish ? ` · ${item.finish}` : ''}</dd></div>
          <div><dt>Color</dt><dd>{item.color_name} · {item.color_mode === 'rainbow' ? 'Rainbow' : item.color_hexes.map((color) => `#${color}`).join(' / ')}</dd></div>
          <div><dt>Diameter</dt><dd>{compactNumber(item.diameter_mm, 2)} mm{item.tolerance_mm ? ` ± ${compactNumber(item.tolerance_mm, 2)} mm` : ''}</dd></div>
          <div><dt>Density</dt><dd>{compactNumber(item.density_g_cm3, 2)} g/cm³</dd></div>
          <div><dt>Nominal net mass</dt><dd>{compactNumber(item.nominal_net_mass_g, 0)} g</dd></div>
          <div><dt>Notes</dt><dd>{item.notes ?? 'No notes'}</dd></div>
        </dl>
      </section>
      <section className="card">
        <header className="card__header"><div><p className="eyebrow">Cura settings</p><h2>Material profile</h2></div>{canEdit && latestProfile && <button className="button" onClick={() => setEditingSettings(true)}><Pencil size={16} /> Edit settings</button>}</header>
        {!latestProfile ? <p className="form-error">No profile exists. Create this filament from a material template.</p> : <dl className="definition-list definition-list--compact"><div><dt>Linked template</dt><dd>{latestProfile.base_template_name ?? 'Missing template'}</dd></div><div><dt>Settings ownership</dt><dd>{latestProfile.override_count ? `${latestProfile.override_count} customized` : 'Fully inherited'}</dd></div><div><dt>Template changes</dt><dd>Inherited automatically</dd></div><div><dt>Printer</dt><dd>{printers.data?.find((printer) => printer.id === latestProfile.printer_id)?.name ?? 'Unknown'} · {compactNumber(latestProfile.nozzle_diameter_mm, 1)} mm</dd></div><div><dt>Resolved Cura settings</dt><dd>{Object.keys(latestProfile.cura_settings).length}</dd></div></dl>}
      </section>
    </div>
    {editingProduct ? <Modal title="Edit filament product" description="Update the canonical product identity and physical specifications." onClose={closeProductEditor} size="wide" footer={<><button className="button" type="button" onClick={closeProductEditor}>Cancel</button><button className="button button--primary" form="edit-filament-product" disabled={update.isPending}><Save size={17} />{update.isPending ? 'Saving…' : 'Save filament'}</button></>}>
      <form id="edit-filament-product" className="editor-form" onSubmit={(event) => { event.preventDefault(); setMessage(''); update.mutate(event.currentTarget) }}>
        <EditorSection title="Product identity" description="Names and the shared screen color sample used throughout the application.">
          <div className="form-grid">
            <label>Vendor<select name="vendor_id" defaultValue={item.vendor_id ?? ''} autoFocus><option value="">Unspecified vendor</option>{vendors.data?.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>
            <label>Display name<input name="product_name" defaultValue={item.product_name ?? ''} maxLength={160} /></label>
            <label>Material type<input name="material_type" value={materialType} onChange={(event) => setMaterialType(event.target.value)} maxLength={48} required /></label>
            <label>Linked material template<select name="material_template_revision_id" value={templateRevisionId || currentTemplateRevisionId} onChange={(event) => setTemplateRevisionId(event.target.value)} required><option value="" disabled>{compatibleTemplateOptions.length ? 'Select a template' : 'No compatible templates'}</option>{compatibleTemplateOptions.map(({ template, revision }) => <option key={revision.id} value={revision.id}>{template.name} · {compactNumber(template.nozzle_diameter_mm, 1)} mm{template.id === latestProfile?.base_template_id ? ' · Current' : ''}</option>)}</select><small className="field-help">Changing this link immediately rebuilds inherited settings while preserving explicit filament customizations.</small></label>
            <FilamentColorEditor name={colorName} mode={colorMode} colorHexes={colorHexes} rememberedColors={colors.data ?? []} onNameChange={setColorName} onModeChange={setColorMode} onColorsChange={setColorHexes} disabled={!item.color_editable} />
            {!item.color_editable ? <p className="security-note form-grid__wide">Color is locked because this filament already has recorded spool use or print history.</p> : null}
          </div>
        </EditorSection>
        <EditorSection title="Physical specifications" description="Dimensions, density, packaged mass, and material modifiers.">
          <div className="form-grid">
            <label>Filament diameter (mm)<input name="diameter_mm" type="number" min="0.1" step="0.01" defaultValue={inputNumber(item.diameter_mm, 2)} required /></label>
            <label>Diameter tolerance (mm)<input name="tolerance_mm" type="number" min="0" step="0.01" defaultValue={inputNumber(item.tolerance_mm, 2)} /></label>
            <label>Density (g/cm³)<input name="density_g_cm3" type="number" min="0.01" step="0.01" defaultValue={inputNumber(item.density_g_cm3, 2)} required /></label>
            <label>Nominal net mass (g)<input name="nominal_net_mass_g" type="number" min="1" step="1" defaultValue={inputNumber(item.nominal_net_mass_g, 0)} required /></label>
            <label>Filler<input name="filler" defaultValue={item.filler ?? ''} maxLength={96} /></label>
            <label>Finish<input name="finish" defaultValue={item.finish ?? ''} maxLength={96} /></label>
            <label className="form-grid__wide">Notes<textarea name="notes" defaultValue={item.notes ?? ''} maxLength={4000} rows={3} /></label>
          </div>
        </EditorSection>
        {update.error ? <p className="form-error" role="alert">{update.error.message}</p> : null}
      </form>
    </Modal> : null}
    {editingSettings && latestProfile ? <Modal title="Edit material profile" description={`Edit resolved values inherited from ${latestProfile.base_template_name ?? 'the linked template'}. Only explicit differences are stored as filament customizations.`} onClose={() => setEditingSettings(false)} size="wide" footer={<><button className="button" type="button" onClick={() => setEditingSettings(false)}>Cancel</button><button className="button button--primary" form="edit-material-profile" disabled={saveProfile.isPending}><Save size={16} />{saveProfile.isPending ? 'Saving…' : 'Save settings'}</button></>}>
      <form id="edit-material-profile" className="editor-form" onSubmit={(event) => { event.preventDefault(); saveProfile.mutate(event.currentTarget) }} key={latestProfile.id}>
        <MaterialSettingsEditor settings={latestProfile} baseSettings={latestProfile.base_template_settings} overrideKeys={latestProfile.override_keys} validationErrors={profileValidationErrors} catalog={catalog.data ?? []} plates={plates.data ?? []} />
        {saveProfile.error ? <p className="form-error" role="alert">{hasProfileValidationErrors ? 'Correct the highlighted values and save again.' : saveProfile.error.message}</p> : null}
      </form>
    </Modal> : null}
  </div>
}
