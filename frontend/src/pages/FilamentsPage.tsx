import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, PackageOpen, Plus, Search } from 'lucide-react'
import { MaterialTypeFilter } from '../components/MaterialTypeFilter'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import type { Filament, FilamentColor, MaterialProfile, MaterialTemplate } from '../api/types'
import { InventoryChoiceSelect } from '../components/NewItemSelect'
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
import { materialIdentitySummary, materialModifierSummary } from '../lib/materialIdentity'

function FilamentIdentity({ filament, hero = false }: { filament: Filament; hero?: boolean }) {
  return <div className="table-identity"><span className={`filament-swatch${hero ? ' filament-swatch--hero' : ''}`} style={filamentSwatchStyle(filament.color_mode, filament.color_hexes, filament.color_hex ?? '2F80A5')} /><span><strong>{filament.vendor_name ?? 'Unspecified manufacturer'}</strong><small>{materialIdentitySummary(filament)}</small></span></div>
}

function FilamentCard({
  filament,
  detailed = false,
  printingTemperature,
  profileCount,
}: {
  filament: Filament
  detailed?: boolean
  printingTemperature: string
  profileCount: number
}) {
  return <Link className={`catalog-card catalog-card--link${detailed ? ' collection-card--detailed' : ''}`} to={`/filaments/${filament.id}`}>
    <span className="filament-swatch filament-swatch--hero" style={filamentSwatchStyle(filament.color_mode, filament.color_hexes, filament.color_hex ?? '2F80A5')} />
    <div><p className="eyebrow">{filament.vendor_name ?? 'Unspecified manufacturer'}</p><h2>{materialIdentitySummary(filament)}</h2></div>
    <dl className="catalog-meta">
      <div><dt>Color</dt><dd>{filament.color_name}</dd></div>
      <div><dt>Tolerance</dt><dd>{filament.tolerance_mm ? `± ${compactNumber(filament.tolerance_mm, 2)} mm` : 'Not specified'}</dd></div>
      <div><dt>Density</dt><dd>{compactNumber(filament.density_g_cm3, 2)} g/cm³</dd></div>
      <div><dt>Printing temperature</dt><dd>{printingTemperature}</dd></div>
      {detailed ? <><div><dt>Print-settings scopes</dt><dd>{profileCount}</dd></div><div><dt>Color changes</dt><dd>{filament.color_editable ? 'Available' : 'Locked by history'}</dd></div></> : null}
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
  const [material, setMaterial] = useState('')
  const [view, setView] = useCollectionView('filaments', 'cards')
  const [showCreate, setShowCreate] = useState(path === '/filaments/new' || Boolean(duplicateSourceId))
  const [createdFilament, setCreatedFilament] = useState<Filament | null>(null)
  const [message, setMessage] = useState('')
  const [colorName, setColorName] = useState('')
  const [colorMode, setColorMode] = useState<FilamentColorMode>('solid')
  const [colorHexes, setColorHexes] = useState(['808080'])
  const filters = new URLSearchParams()
  if (search) filters.set('search', search)
  if (material) filters.set('material', material)
  const query = useQuery({ queryKey: ['filaments', search, material], queryFn: () => apiFetch<Filament[]>(`/filaments${filters.size ? `?${filters}` : ''}`) })
  const duplicateSource = useQuery({
    queryKey: ['filament', duplicateSourceId],
    queryFn: () => apiFetch<Filament>(`/filaments/${duplicateSourceId}`),
    enabled: Boolean(duplicateSourceId),
  })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates') })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
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
  const profilePresentation = useMemo(() => {
    const grouped = new Map<string, number[]>()
    for (const profile of profiles.data ?? []) {
      const temperatures = grouped.get(profile.filament_product_id) ?? []
      const temperature = Number(profile.extruder_temp_c)
      if (Number.isFinite(temperature)) temperatures.push(temperature)
      grouped.set(profile.filament_product_id, temperatures)
    }
    return new Map(Array.from(grouped, ([filamentId, temperatures]) => {
      const unique = Array.from(new Set(temperatures)).sort((left, right) => left - right)
      const temperature = !unique.length
        ? 'Not configured'
        : unique.length === 1
          ? `${compactNumber(unique[0], 0)} °C`
          : `${compactNumber(unique[0], 0)}–${compactNumber(unique[unique.length - 1], 0)} °C`
      return [filamentId, { temperature, count: temperatures.length }]
    }))
  }, [profiles.data])
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
          // Rainbow owns a fixed six-sample display palette on the server.
          // User requests retain the separate one-to-three multicolor limit.
          color_hexes: colorMode === 'rainbow' ? [] : colorHexes,
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
      setMessage('Filament created with its first printer/nozzle print-settings scope.')
      setColorName('')
      setColorMode('solid')
      setColorHexes(['808080'])
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['filaments'] }),
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
      ])
      setShowCreate(false)
      setCreatedFilament(created)
    },
    onError: (error: Error) => setMessage(error.message),
  })

  function dismissCreatedFilament() {
    const createdId = createdFilament?.id
    setCreatedFilament(null)
    if (duplicateSourceId && createdId) navigate(`/filaments/${createdId}`, true)
    else if (path === '/filaments/new') navigate('/filaments', true)
  }
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage('')
    create.mutate(event.currentTarget)
  }
  return <div><PageHeader eyebrow="Product catalog" title="Filaments" description="Real filament products with physical identity, inventory, and printer/nozzle-specific print settings." actions={<><FilamentSectionNav />{user?.role !== 'viewer' ? <button className="button button--primary" onClick={() => setShowCreate(true)}><Plus size={17} /> Add filament</button> : null}</>} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    <section className="toolbar"><label className="search-field"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search type, color, filler, or finish" aria-label="Search filaments" /></label><MaterialTypeFilter templates={templates.data ?? []} value={material} onChange={setMaterial} /><CollectionViewSelector label="Filaments" value={view} onChange={setView} /><span className="toolbar__summary">{query.data?.length ?? 0} products</span></section>{query.isLoading || profiles.isLoading ? <LoadingState /> : !query.data?.length ? <EmptyState icon={PackageOpen} title="No filament products" description="Add a material template, then add the first filament product here." /> : view === 'list' ? <div className="table-card collection-table"><table><thead><tr><th>Filament</th><th>Modifiers</th><th>Diameter</th><th>Density</th><th>Nominal</th><th>Print settings</th></tr></thead><tbody>{query.data.map((filament) => <tr key={filament.id} tabIndex={0} onClick={() => navigate(`/filaments/${filament.id}`)} onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && navigate(`/filaments/${filament.id}`)}><td><FilamentIdentity filament={filament} /></td><td>{materialModifierSummary(filament) ?? 'Standard material'}</td><td>{compactNumber(filament.diameter_mm, 2)} mm</td><td>{compactNumber(filament.density_g_cm3, 2)} g/cm³</td><td>{grams(filament.nominal_net_mass_g)}</td><td>{filament.material_template_revision_id ? 'Available' : 'Unavailable'}</td></tr>)}</tbody></table></div> : <section className={`collection-grid collection-grid--${view}`}>{query.data.map((filament) => { const presentation = profilePresentation.get(filament.id); return <FilamentCard key={filament.id} filament={filament} detailed={view === 'detailed'} printingTemperature={presentation?.temperature ?? 'Not configured'} profileCount={presentation?.count ?? 0} /> })}</section>}
    {showCreate ? <Modal title={duplicateSourceId ? 'Duplicate filament' : 'Add a filament'} description={duplicateSourceId ? 'Create a separate product with the source filament’s product details and explicit settings for the selected source scope. Spools and history are not copied.' : 'This creates the filament and its first print-settings scope. Additional printer/nozzle settings can be added from the filament later.'} onClose={closeCreate} size="wide" footer={<><button className="button" type="button" onClick={closeCreate}>Cancel</button><button className="button button--primary" form="create-filament" disabled={create.isPending || !selectableTemplates.length || (Boolean(duplicateSourceId) && duplicateSource.isLoading)}><Plus size={17} />{create.isPending ? 'Creating…' : duplicateSourceId ? 'Create duplicate' : 'Create filament'}</button></>}>
      {duplicateSource.error ? <p className="form-error" role="alert">{duplicateSource.error.message}</p> : selectableTemplates.length && (!duplicateSourceId || duplicateSource.data) ? <form id="create-filament" className="editor-form" onSubmit={submit} key={duplicateSource.data?.id ?? 'new'}>
        <EditorSection title="Product identity" description="Choose the starting print-settings scope and the labels operators see throughout inventory.">
          <div className="form-grid">
            <label>Starting template<select name="material_template_revision_id" defaultValue={duplicateSource.data?.material_template_revision_id ?? ''} required autoFocus>{selectableTemplates.map(({ template, settingsSnapshot }) => <option key={settingsSnapshot.id} value={settingsSnapshot.id}>{template.name} · {compactNumber(template.nozzle_diameter_mm, 1)} mm</option>)}</select></label>
            <label>Manufacturer<InventoryChoiceSelect kind="manufacturer" name="vendor_id" defaultValue={duplicateSource.data?.vendor_id ?? ''} /></label>
            <FilamentColorEditor name={colorName} mode={colorMode} colorHexes={colorHexes} rememberedColors={colors.data ?? []} onNameChange={setColorName} onModeChange={setColorMode} onColorsChange={setColorHexes} />
          </div>
        </EditorSection>
        <EditorSection title="Physical specifications" description="Record the diameter, density, packaged mass, and material modifiers.">
          <div className="form-grid">
            <label>Filament diameter (mm)<input name="diameter_mm" type="number" min="0.1" step="0.01" defaultValue={duplicateSource.data?.diameter_mm ?? '1.75'} required /></label>
            <label>Diameter tolerance (mm)<input name="tolerance_mm" type="number" min="0" step="0.01" defaultValue={duplicateSource.data?.tolerance_mm ?? ''} /></label>
            <label>Density (g/cm³)<input name="density_g_cm3" type="number" min="0.01" step="0.01" defaultValue={duplicateSource.data?.density_g_cm3 ?? '1.24'} required /></label>
            <label>Nominal net mass (g)<input name="nominal_net_mass_g" type="number" min="1" step="1" defaultValue={duplicateSource.data?.nominal_net_mass_g ?? '1000'} required /></label>
            <label>Filler<InventoryChoiceSelect kind="filler" name="filler" defaultValue={duplicateSource.data?.filler ?? 'None'} /></label>
            <label>Finish<InventoryChoiceSelect kind="finish" name="finish" defaultValue={duplicateSource.data?.finish ?? 'Standard'} /></label>
            <label className="form-grid__wide">Notes<textarea name="notes" defaultValue={duplicateSource.data?.notes ?? ''} rows={3} maxLength={4000} /></label>
          </div>
        </EditorSection>
        {create.error ? <p className="form-error" role="alert">{create.error.message}</p> : null}
      </form> : <p className="form-error">Add at least one material template before adding filament products.</p>}
    </Modal> : null}
    {createdFilament ? <Modal title="Create a spool?" description={`${materialIdentitySummary(createdFilament)} is ready. Would you like to add its first physical spool now?`} onClose={dismissCreatedFilament} footer={<><button className="button" type="button" onClick={dismissCreatedFilament}>Not now</button><button className="button button--primary" type="button" onClick={() => navigate(`/spools?create=1&filament_id=${encodeURIComponent(createdFilament.id)}`)}><Plus size={17} /> Add spool</button></>}><p className="muted">The new spool form will open with this filament selected.</p></Modal> : null}
  </div>
}
