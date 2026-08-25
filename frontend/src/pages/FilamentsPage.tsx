import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, PackageOpen, Plus, Search } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import type { Filament, FilamentColor, MaterialTemplate, Vendor } from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { CollectionViewSelector } from '../components/CollectionViewSelector'
import { FilamentColorEditor, type FilamentColorMode } from '../components/FilamentColorEditor'
import { FilamentSectionNav } from '../components/FilamentSectionNav'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../context/AuthContext'
import { Link, useRouter } from '../context/RouterContext'
import { useCollectionView } from '../hooks/useCollectionView'
import { filamentSwatchStyle } from '../lib/colors'
import { compactNumber, grams } from '../lib/format'

function FilamentIdentity({ filament, hero = false }: { filament: Filament; hero?: boolean }) {
  return <div className="table-identity"><span className={`filament-swatch${hero ? ' filament-swatch--hero' : ''}`} style={filamentSwatchStyle(filament.color_mode, filament.color_hexes, filament.color_hex ?? '2F80A5')} /><span><strong>{filament.vendor_name ?? 'Unspecified vendor'}</strong><small>{filament.material_type} · {filament.color_name}{filament.product_name ? ` · ${filament.product_name}` : ''}</small></span></div>
}

function FilamentCard({ filament, detailed = false }: { filament: Filament; detailed?: boolean }) {
  return <Link className={`catalog-card catalog-card--link${detailed ? ' collection-card--detailed' : ''}`} to={`/filaments/${filament.id}`}>
    <span className="filament-swatch filament-swatch--hero" style={filamentSwatchStyle(filament.color_mode, filament.color_hexes, filament.color_hex ?? '2F80A5')} />
    <div><p className="eyebrow">{filament.vendor_name ?? 'Unspecified vendor'}</p><h2>{filament.material_type} · {filament.color_name}{filament.product_name ? ` · ${filament.product_name}` : ''}</h2><p>{filament.filler ?? 'No filler'} / {filament.finish ?? 'Standard finish'}</p></div>
    <dl className="catalog-meta">
      <div><dt>Color</dt><dd>{filament.color_name}</dd></div>
      <div><dt>Diameter</dt><dd>{compactNumber(filament.diameter_mm, 2)} mm</dd></div>
      <div><dt>Density</dt><dd>{compactNumber(filament.density_g_cm3, 2)} g/cm³</dd></div>
      <div><dt>Nominal</dt><dd>{grams(filament.nominal_net_mass_g)}</dd></div>
      {detailed ? <><div><dt>Tolerance</dt><dd>{filament.tolerance_mm ? `${compactNumber(filament.tolerance_mm, 2)} mm` : 'Not specified'}</dd></div><div><dt>Color changes</dt><dd>{filament.color_editable ? 'Available' : 'Locked by history'}</dd></div></> : null}
    </dl>
    {detailed && filament.notes ? <p className="collection-card__notes">{filament.notes}</p> : null}
    <p className={filament.material_template_revision_id ? 'success-note' : 'warning-note'}>{filament.material_template_revision_id ? 'Print settings available' : 'Starting template unavailable'}</p>
    {detailed ? <span className="collection-card__link">Open filament <ArrowRight size={16} /></span> : null}
  </Link>
}

export default function FilamentsPage() {
  const { path, navigate } = useRouter()
  const duplicateSourceId = path.match(/^\/filaments\/duplicate\/([0-9a-f-]{36})$/i)?.[1] ?? ''
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [view, setView] = useCollectionView('filaments', 'cards')
  const [showCreate, setShowCreate] = useState(path === '/filaments/new' || Boolean(duplicateSourceId))
  const [message, setMessage] = useState('')
  const [colorName, setColorName] = useState('')
  const [colorMode, setColorMode] = useState<FilamentColorMode>('solid')
  const [colorHexes, setColorHexes] = useState(['808080'])
  const query = useQuery({ queryKey: ['filaments', search], queryFn: () => apiFetch<Filament[]>(`/filaments${search ? `?search=${encodeURIComponent(search)}` : ''}`) })
  const duplicateSource = useQuery({
    queryKey: ['filament', duplicateSourceId],
    queryFn: () => apiFetch<Filament>(`/filaments/${duplicateSourceId}`),
    enabled: Boolean(duplicateSourceId),
  })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates') })
  const vendors = useQuery({ queryKey: ['vendors'], queryFn: () => apiFetch<Vendor[]>('/vendors') })
  const colors = useQuery({ queryKey: ['filament-colors'], queryFn: () => apiFetch<FilamentColor[]>('/filament-colors') })
  useEffect(() => {
    if (path === '/filaments/new' || duplicateSourceId) setShowCreate(true)
  }, [duplicateSourceId, path])
  useEffect(() => {
    if (!duplicateSource.data) return
    setColorName(duplicateSource.data.color_name)
    setColorMode(duplicateSource.data.color_mode)
    setColorHexes(duplicateSource.data.color_hexes.length ? duplicateSource.data.color_hexes : [duplicateSource.data.color_hex ?? '808080'])
  }, [duplicateSource.data])
  const closeCreate = () => {
    setShowCreate(false)
    if (path === '/filaments/new' || duplicateSourceId) navigate('/filaments', true)
  }
  const currentTemplates = (templates.data ?? []).flatMap((template) => {
    const settingsSnapshot = template.revisions[0]
    return settingsSnapshot ? [{ template, settingsSnapshot }] : []
  })
  const selectableTemplates = duplicateSource.data
    ? currentTemplates.filter(({ settingsSnapshot }) => settingsSnapshot.id === duplicateSource.data?.material_template_revision_id)
    : currentTemplates
  const create = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form)
      const selected = selectableTemplates.find((item) => item.settingsSnapshot.id === data.get('material_template_revision_id'))
      if (!selected) throw new Error('Select a material template')
      return apiFetch<Filament>('/filaments', {
        method: 'POST',
        body: JSON.stringify({
          vendor_id: String(data.get('vendor_id') ?? '') || null,
          material_type: selected.template.material_type,
          filler: String(data.get('filler') ?? '').trim() || null,
          finish: String(data.get('finish') ?? '').trim() || null,
          color_name: colorName.trim(),
          color_hex: colorHexes[0],
          color_mode: colorMode,
          color_hexes: colorHexes,
          product_name: String(data.get('product_name') ?? '').trim() || null,
          diameter_mm: String(data.get('diameter_mm')),
          tolerance_mm: String(data.get('tolerance_mm') ?? '').trim() || null,
          density_g_cm3: String(data.get('density_g_cm3')),
          nominal_net_mass_g: String(data.get('nominal_net_mass_g')),
          notes: String(data.get('notes') ?? '').trim() || null,
          material_template_revision_id: selected.settingsSnapshot.id,
          duplicate_source_filament_id: duplicateSourceId || null,
        }),
      })
    },
    onSuccess: async (created) => {
      setMessage('Filament created with its first printer/nozzle print-settings scope. Matching template changes inherit automatically except for explicit customizations.')
      setColorName('')
      setColorMode('solid')
      setColorHexes(['808080'])
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['filaments'] }),
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
      ])
      if (duplicateSourceId) navigate(`/filaments/${created.id}`, true)
      else closeCreate()
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage('')
    create.mutate(event.currentTarget)
  }
  return <div><FilamentSectionNav /><PageHeader eyebrow="Product catalog" title="Filaments" description="Real filament products with physical identity, inventory, and printer/nozzle-specific print settings." actions={user?.role !== 'viewer' ? <button className="button button--primary" onClick={() => setShowCreate(true)}><Plus size={17} /> Add filament</button> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    <section className="toolbar"><label className="search-field"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search material, product, or color" aria-label="Search filaments" /></label><CollectionViewSelector label="Filaments" value={view} onChange={setView} /><span className="toolbar__summary">{query.data?.length ?? 0} products</span></section>{query.isLoading ? <LoadingState /> : !query.data?.length ? <EmptyState icon={PackageOpen} title="No filament products" description="Add a material template, then add the first filament product here." /> : view === 'list' ? <div className="table-card collection-table"><table><thead><tr><th>Filament</th><th>Modifiers</th><th>Diameter</th><th>Density</th><th>Nominal</th><th>Print settings</th></tr></thead><tbody>{query.data.map((filament) => <tr key={filament.id} tabIndex={0} onClick={() => navigate(`/filaments/${filament.id}`)} onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && navigate(`/filaments/${filament.id}`)}><td><FilamentIdentity filament={filament} /></td><td>{filament.filler ?? 'No filler'}<small className="table-subtext">{filament.finish ?? 'Standard finish'}</small></td><td>{compactNumber(filament.diameter_mm, 2)} mm</td><td>{compactNumber(filament.density_g_cm3, 2)} g/cm³</td><td>{grams(filament.nominal_net_mass_g)}</td><td>{filament.material_template_revision_id ? 'Available' : 'Unavailable'}</td></tr>)}</tbody></table></div> : <section className={`collection-grid collection-grid--${view}`}>{query.data.map((filament) => <FilamentCard key={filament.id} filament={filament} detailed={view === 'detailed'} />)}</section>}
    {showCreate ? <Modal title={duplicateSourceId ? 'Duplicate filament' : 'Add a filament'} description={duplicateSourceId ? 'Create a separate product with the source filament’s product details and explicit settings for the selected source scope. Spools and history are not copied.' : 'This creates the filament and its first print-settings scope. Additional printer/nozzle settings can be added from the filament later.'} onClose={closeCreate} size="wide" footer={<><button className="button" type="button" onClick={closeCreate}>Cancel</button><button className="button button--primary" form="create-filament" disabled={create.isPending || !selectableTemplates.length || (Boolean(duplicateSourceId) && duplicateSource.isLoading)}><Plus size={17} />{create.isPending ? 'Creating…' : duplicateSourceId ? 'Create duplicate' : 'Create filament'}</button></>}>
      {duplicateSource.error ? <p className="form-error" role="alert">{duplicateSource.error.message}</p> : selectableTemplates.length && (!duplicateSourceId || duplicateSource.data) ? <form id="create-filament" className="editor-form" onSubmit={submit} key={duplicateSource.data?.id ?? 'new'}>
        <EditorSection title="Product identity" description="Choose the starting print-settings scope and the labels operators see throughout inventory.">
          <div className="form-grid">
            <label>Starting template<select name="material_template_revision_id" defaultValue={duplicateSource.data?.material_template_revision_id ?? ''} required autoFocus>{selectableTemplates.map(({ template, settingsSnapshot }) => <option key={settingsSnapshot.id} value={settingsSnapshot.id}>{template.name} · {compactNumber(template.nozzle_diameter_mm, 1)} mm</option>)}</select></label>
            <label>Vendor<select name="vendor_id" defaultValue={duplicateSource.data?.vendor_id ?? ''}><option value="">Unspecified vendor</option>{vendors.data?.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>
            <label>Display name<input name="product_name" defaultValue={duplicateSource.data ? `${duplicateSource.data.product_name ?? `${duplicateSource.data.material_type} ${duplicateSource.data.color_name}`} Copy` : ''} maxLength={160} placeholder="PolyLite PLA" /></label>
            <FilamentColorEditor name={colorName} mode={colorMode} colorHexes={colorHexes} rememberedColors={colors.data ?? []} onNameChange={setColorName} onModeChange={setColorMode} onColorsChange={setColorHexes} />
          </div>
        </EditorSection>
        <EditorSection title="Physical specifications" description="Record the diameter, density, packaged mass, and material modifiers.">
          <div className="form-grid">
            <label>Filament diameter (mm)<input name="diameter_mm" type="number" min="0.1" step="0.01" defaultValue={duplicateSource.data?.diameter_mm ?? '1.75'} required /></label>
            <label>Diameter tolerance (mm)<input name="tolerance_mm" type="number" min="0" step="0.01" defaultValue={duplicateSource.data?.tolerance_mm ?? ''} /></label>
            <label>Density (g/cm³)<input name="density_g_cm3" type="number" min="0.01" step="0.01" defaultValue={duplicateSource.data?.density_g_cm3 ?? '1.24'} required /></label>
            <label>Nominal net mass (g)<input name="nominal_net_mass_g" type="number" min="1" step="1" defaultValue={duplicateSource.data?.nominal_net_mass_g ?? '1000'} required /></label>
            <label>Filler<input name="filler" defaultValue={duplicateSource.data?.filler ?? ''} maxLength={96} placeholder="Carbon fiber, glass…" /></label>
            <label>Finish<input name="finish" defaultValue={duplicateSource.data?.finish ?? ''} maxLength={96} placeholder="Matte, silk…" /></label>
            <label className="form-grid__wide">Notes<textarea name="notes" defaultValue={duplicateSource.data?.notes ?? ''} rows={3} maxLength={4000} /></label>
          </div>
        </EditorSection>
        {create.error ? <p className="form-error" role="alert">{create.error.message}</p> : null}
      </form> : <p className="form-error">Add at least one material template before adding filament products.</p>}
    </Modal> : null}
  </div>
}
