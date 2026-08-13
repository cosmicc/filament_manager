import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CopyPlus, GitCompareArrows, Pencil, Save, Upload } from 'lucide-react'
import { type CSSProperties, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import type {
  BuildPlate,
  CuraSettingCatalogItem,
  Filament,
  FilamentColor,
  MaterialProfile,
  Printer,
  Vendor,
} from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { LoadingState } from '../components/LoadingState'
import { MaterialSettingsEditor, settingsFromForm } from '../components/MaterialSettingsEditor'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { Link, useRouter } from '../context/RouterContext'

function optional(data: FormData, key: string) {
  const value = String(data.get(key) ?? '').trim()
  return value || null
}

export default function FilamentDetailPage() {
  const { path } = useRouter()
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
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const catalog = useQuery({ queryKey: ['cura-settings-catalog'], queryFn: () => apiFetch<CuraSettingCatalogItem[]>('/profiles/cura-settings/catalog') })
  const [colorName, setColorName] = useState('')
  const [colorHex, setColorHex] = useState('#808080')
  const [editingProduct, setEditingProduct] = useState(false)
  const [editingSettings, setEditingSettings] = useState(false)
  const [reviewingTemplateUpdate, setReviewingTemplateUpdate] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!filament.data) return
    setColorName(filament.data.color_name)
    setColorHex(`#${filament.data.color_hex ?? '808080'}`)
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
          material_type: String(data.get('material_type') ?? '').trim(),
          color_name: colorName.trim(),
          color_hex: colorHex.replace('#', ''),
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
  const saveProfile = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      if (!latestProfile) throw new Error('This filament does not have a starting profile')
      return apiFetch<MaterialProfile>(`/profiles/${latestProfile.id}/revisions`, {
        method: 'POST',
        body: JSON.stringify({
          expected_profile_version: latestProfile.record_version,
          settings: settingsFromForm(form, catalog.data ?? []),
        }),
      })
    },
    onSuccess: async () => {
      setMessage('Settings saved as a new template-linked draft with only customized values stored.')
      setEditingSettings(false)
      await client.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const publish = useMutation({
    mutationFn: (profileId: string) => apiFetch(`/profiles/${profileId}/publish`, { method: 'POST' }),
    onSuccess: async () => {
      setMessage('Profile published and ready for Cura synchronization.')
      await client.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const updateTemplateBase = useMutation({
    mutationFn: () => {
      if (!latestProfile?.latest_template_revision_id) throw new Error('No template update is available')
      return apiFetch<MaterialProfile>(`/profiles/${latestProfile.id}/template-base`, {
        method: 'POST',
        body: JSON.stringify({
          expected_profile_version: latestProfile.record_version,
          target_template_revision_id: latestProfile.latest_template_revision_id,
        }),
      })
    },
    onSuccess: async () => {
      setMessage('Template update confirmed for this filament and saved as a reviewable draft profile.')
      setReviewingTemplateUpdate(false)
      await client.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })

  if (filament.isLoading) return <LoadingState label="Loading filament details" />
  if (!filament.data) return <div><Link className="button" to="/filaments"><ArrowLeft size={16} /> Filaments</Link><p className="form-error">{filament.error?.message ?? 'Filament not found'}</p></div>
  const item = filament.data
  const selectColorName = (name: string) => {
    setColorName(name)
    const normalized = name.normalize('NFKC').trim().toLocaleLowerCase()
    const remembered = colors.data?.find((color) => color.normalized_name === normalized)
    if (remembered) setColorHex(`#${remembered.color_hex}`)
  }
  const closeProductEditor = () => {
    setColorName(item.color_name)
    setColorHex(`#${item.color_hex ?? '808080'}`)
    setEditingProduct(false)
  }

  return <div>
    <PageHeader
      eyebrow={`${item.vendor_name ?? 'Unspecified vendor'} · ${item.material_type}`}
      title={item.product_name ?? `${item.material_type} ${item.color_name}`}
      description="Edit canonical product details and every Cura material setting stored for this filament."
      actions={<Link className="button" to="/filaments"><ArrowLeft size={16} /> All filaments</Link>}
    />
    {message && <div className="deployment-note" role="status">{message}</div>}
    <div className="detail-grid">
      <section className="card product-editor">
        <header className="card__header"><div><p className="eyebrow">Canonical filament</p><h2>Product details</h2></div><div className="card-header-actions"><span className="filament-swatch" style={{ '--swatch': colorHex } as CSSProperties} />{canEdit ? <button className="button" onClick={() => setEditingProduct(true)}><Pencil size={16} /> Edit</button> : null}</div></header>
        <dl className="definition-list">
          <div><dt>Vendor and product</dt><dd>{item.vendor_name ?? 'Unspecified vendor'} · {item.product_name ?? 'No product name'}</dd></div>
          <div><dt>Material</dt><dd>{item.material_type}{item.filler ? ` · ${item.filler}` : ''}{item.finish ? ` · ${item.finish}` : ''}</dd></div>
          <div><dt>Color</dt><dd>{item.color_name} · #{item.color_hex ?? '808080'}</dd></div>
          <div><dt>Diameter</dt><dd>{item.diameter_mm} mm{item.tolerance_mm ? ` ± ${item.tolerance_mm} mm` : ''}</dd></div>
          <div><dt>Density</dt><dd>{item.density_g_cm3} g/cm³</dd></div>
          <div><dt>Nominal net mass</dt><dd>{item.nominal_net_mass_g} g</dd></div>
          <div><dt>Notes</dt><dd>{item.notes ?? 'No notes'}</dd></div>
        </dl>
      </section>
      <section className="card">
        <header className="card__header"><div><p className="eyebrow">Versioned Cura settings</p><h2>Material profile</h2></div>{canEdit && latestProfile && <button className="button" onClick={() => setEditingSettings(true)}><CopyPlus size={16} /> Edit as new version</button>}</header>
        {!latestProfile ? <p className="form-error">No profile exists. Create this filament from a published material template.</p> : <>
          <dl className="definition-list definition-list--compact"><div><dt>Latest version</dt><dd>v{latestProfile.version}</dd></div><div><dt>Status</dt><dd><StatusPill status={latestProfile.status} /></dd></div><div><dt>Linked template</dt><dd>{latestProfile.base_template_name ?? 'Missing template'} · v{latestProfile.base_template_version ?? '—'}</dd></div><div><dt>Settings ownership</dt><dd>{latestProfile.override_count ? `${latestProfile.override_count} customized` : 'Fully inherited'}</dd></div><div><dt>Printer</dt><dd>{printers.data?.find((printer) => printer.id === latestProfile.printer_id)?.name ?? 'Unknown'} · {latestProfile.nozzle_diameter_mm} mm</dd></div><div><dt>Resolved Cura settings</dt><dd>{Object.keys(latestProfile.cura_settings).length}</dd></div></dl>
          {latestProfile.latest_template_revision_id !== latestProfile.base_template_revision_id ? <div className="publish-banner"><div><strong>{latestProfile.base_template_name} v{latestProfile.latest_template_version} is available</strong><p>Review and confirm this template change for this filament only. Existing overrides are preserved.</p></div>{canEdit ? <button className="button" onClick={() => setReviewingTemplateUpdate(true)}><GitCompareArrows size={16} /> Review template update</button> : null}</div> : null}
          <div className="profile-version-list">{productProfiles.map((profile) => <div key={profile.id}><span>v{profile.version} · {profile.base_template_name ?? 'Template'} v{profile.base_template_version ?? '—'} · {profile.override_count ? `${profile.override_count} overrides` : 'inherited'}</span><div><StatusPill status={profile.status} />{canEdit && profile.status !== 'published' && <button className="icon-button" title="Publish profile" onClick={() => publish.mutate(profile.id)} disabled={publish.isPending}><Upload size={16} /></button>}</div></div>)}</div>
        </>}
      </section>
    </div>
    {editingProduct ? <Modal title="Edit filament product" description="Update the canonical product identity and physical specifications." onClose={closeProductEditor} size="wide" footer={<><button className="button" type="button" onClick={closeProductEditor}>Cancel</button><button className="button button--primary" form="edit-filament-product" disabled={update.isPending}><Save size={17} />{update.isPending ? 'Saving…' : 'Save filament'}</button></>}>
      <form id="edit-filament-product" className="editor-form" onSubmit={(event) => { event.preventDefault(); setMessage(''); update.mutate(event.currentTarget) }}>
        <EditorSection title="Product identity" description="Names and the shared screen color sample used throughout the application.">
          <div className="form-grid">
            <label>Vendor<select name="vendor_id" defaultValue={item.vendor_id ?? ''} autoFocus><option value="">Unspecified vendor</option>{vendors.data?.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>
            <label>Product name<input name="product_name" defaultValue={item.product_name ?? ''} maxLength={160} /></label>
            <label>Material type<input name="material_type" defaultValue={item.material_type} maxLength={48} required /></label>
            <label>Color name<input list="remembered-colors" value={colorName} onChange={(event) => selectColorName(event.target.value)} maxLength={96} required /><datalist id="remembered-colors">{colors.data?.map((color) => <option key={color.id} value={color.name} />)}</datalist></label>
            <label>Screen color sample<input type="color" value={colorHex} onChange={(event) => setColorHex(event.target.value.toUpperCase())} /><small className="field-help">Remembered globally for “{colorName || 'this color'}”.</small></label>
          </div>
        </EditorSection>
        <EditorSection title="Physical specifications" description="Dimensions, density, packaged mass, and material modifiers.">
          <div className="form-grid">
            <label>Filament diameter (mm)<input name="diameter_mm" type="number" min="0.1" step="0.01" defaultValue={item.diameter_mm} required /></label>
            <label>Diameter tolerance (mm)<input name="tolerance_mm" type="number" min="0" step="0.001" defaultValue={item.tolerance_mm ?? ''} /></label>
            <label>Density (g/cm³)<input name="density_g_cm3" type="number" min="0.01" step="0.001" defaultValue={item.density_g_cm3} required /></label>
            <label>Nominal net mass (g)<input name="nominal_net_mass_g" type="number" min="1" step="0.1" defaultValue={item.nominal_net_mass_g} required /></label>
            <label>Filler<input name="filler" defaultValue={item.filler ?? ''} maxLength={96} /></label>
            <label>Finish<input name="finish" defaultValue={item.finish ?? ''} maxLength={96} /></label>
            <label className="form-grid__wide">Notes<textarea name="notes" defaultValue={item.notes ?? ''} maxLength={4000} rows={3} /></label>
          </div>
        </EditorSection>
        {update.error ? <p className="form-error" role="alert">{update.error.message}</p> : null}
      </form>
    </Modal> : null}
    {editingSettings && latestProfile ? <Modal title={`Edit material profile v${latestProfile.version + 1}`} description={`Edit resolved values inherited from ${latestProfile.base_template_name ?? 'the linked template'}. Only differences are stored as filament overrides.`} onClose={() => setEditingSettings(false)} size="wide" footer={<><button className="button" type="button" onClick={() => setEditingSettings(false)}>Cancel</button><button className="button button--primary" form="edit-material-profile" disabled={saveProfile.isPending}><CopyPlus size={16} />{saveProfile.isPending ? 'Saving…' : 'Save new draft version'}</button></>}>
      <form id="edit-material-profile" className="editor-form" onSubmit={(event) => { event.preventDefault(); saveProfile.mutate(event.currentTarget) }} key={latestProfile.id}>
        <MaterialSettingsEditor settings={latestProfile} baseSettings={latestProfile.base_template_settings} overrideKeys={latestProfile.override_keys} catalog={catalog.data ?? []} plates={plates.data ?? []} />
        {saveProfile.error ? <p className="form-error" role="alert">{saveProfile.error.message}</p> : null}
      </form>
    </Modal> : null}
    {reviewingTemplateUpdate && latestProfile ? <Modal title={`Update ${latestProfile.base_template_name} base`} description={`This confirmation applies only to ${item.product_name ?? `${item.material_type} ${item.color_name}`}. It creates a draft profile; nothing is published automatically.`} onClose={() => setReviewingTemplateUpdate(false)} size="wide" footer={<><button className="button" type="button" onClick={() => setReviewingTemplateUpdate(false)}>Keep v{latestProfile.base_template_version}</button><button className="button button--primary" type="button" disabled={updateTemplateBase.isPending} onClick={() => updateTemplateBase.mutate()}><GitCompareArrows size={16} />{updateTemplateBase.isPending ? 'Creating draft…' : `Confirm v${latestProfile.latest_template_version}`}</button></>}>
      <EditorSection title="Effective setting changes" description="Customized values remain unchanged. Listed inherited values will change when this draft is published.">
        {latestProfile.template_update_changes.length ? <div className="comparison-table"><div className="comparison-row comparison-row--header"><div>Setting</div><div>Current</div><div>Proposed</div></div>{latestProfile.template_update_changes.map((change) => {
          const label = catalog.data?.find((entry) => entry.key === change.key)?.label ?? change.key.replaceAll('_', ' ')
          return <div className="comparison-row" key={change.key}><div className="comparison-setting"><strong>{label}</strong><small>{change.overridden ? 'Customized value preserved' : 'Inherited from template'}</small></div><div className="comparison-value">{String(change.current_value ?? 'Not set')}</div><div className="comparison-value">{String(change.proposed_value ?? 'Not set')}</div></div>
        })}</div> : <p className="success-note">Your overrides produce no effective setting changes, but you may still confirm the newer template base.</p>}
      </EditorSection>
      {updateTemplateBase.error ? <p className="form-error" role="alert">{updateTemplateBase.error.message}</p> : null}
    </Modal> : null}
  </div>
}
