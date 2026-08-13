import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PackageOpen, Plus, Search } from 'lucide-react'
import { type CSSProperties, type FormEvent, useState } from 'react'
import { apiFetch } from '../api/client'
import type { Filament, FilamentColor, MaterialTemplate, Vendor } from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../context/AuthContext'
import { Link } from '../context/RouterContext'
import { grams } from '../lib/format'

export default function FilamentsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [message, setMessage] = useState('')
  const [colorName, setColorName] = useState('')
  const [colorHex, setColorHex] = useState('#808080')
  const query = useQuery({ queryKey: ['filaments', search], queryFn: () => apiFetch<Filament[]>(`/filaments${search ? `?search=${encodeURIComponent(search)}` : ''}`) })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates') })
  const vendors = useQuery({ queryKey: ['vendors'], queryFn: () => apiFetch<Vendor[]>('/vendors') })
  const colors = useQuery({ queryKey: ['filament-colors'], queryFn: () => apiFetch<FilamentColor[]>('/filament-colors') })
  const publishedTemplates = (templates.data ?? []).flatMap((template) => {
    const revision = template.revisions.find((item) => item.status === 'published')
    return revision ? [{ template, revision }] : []
  })
  const create = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form)
      const selected = publishedTemplates.find((item) => item.revision.id === data.get('material_template_revision_id'))
      if (!selected) throw new Error('Select a published material template')
      return apiFetch('/filaments', {
        method: 'POST',
        body: JSON.stringify({
          vendor_id: String(data.get('vendor_id') ?? '') || null,
          material_type: selected.template.material_type,
          filler: String(data.get('filler') ?? '').trim() || null,
          finish: String(data.get('finish') ?? '').trim() || null,
          color_name: colorName.trim(),
          color_hex: colorHex.replace('#', ''),
          product_name: String(data.get('product_name') ?? '').trim() || null,
          diameter_mm: String(data.get('diameter_mm')),
          tolerance_mm: String(data.get('tolerance_mm') ?? '').trim() || null,
          density_g_cm3: String(data.get('density_g_cm3')),
          nominal_net_mass_g: String(data.get('nominal_net_mass_g')),
          notes: String(data.get('notes') ?? '').trim() || null,
          material_template_revision_id: selected.revision.id,
        }),
      })
    },
    onSuccess: async () => {
      setMessage('Filament product created with a draft profile linked to its published template base.')
      setShowCreate(false)
      setColorName('')
      setColorHex('#808080')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['filaments'] }),
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
      ])
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage('')
    create.mutate(event.currentTarget)
  }
  return <div><PageHeader eyebrow="Product catalog" title="Filaments" description="Real filament products linked to published template bases with only their customized settings stored as overrides." actions={user?.role !== 'viewer' ? <button className="button button--primary" onClick={() => setShowCreate(true)}><Plus size={17} /> Add filament</button> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    <section className="toolbar"><label className="search-field"><Search size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search material, product, or color" aria-label="Search filaments" /></label><span className="toolbar__summary">{query.data?.length ?? 0} products</span></section>{query.isLoading ? <LoadingState /> : !query.data?.length ? <EmptyState icon={PackageOpen} title="No filament products" description="Publish a material template, then add the first filament product here." /> : <section className="catalog-grid">{query.data.map((filament) => <Link className="catalog-card catalog-card--link" to={`/filaments/${filament.id}`} key={filament.id}><span className="filament-swatch filament-swatch--hero" style={{ '--swatch': `#${filament.color_hex ?? '2F80A5'}` } as CSSProperties} /><div><p className="eyebrow">{filament.vendor_name ?? 'Unspecified vendor'}</p><h2>{filament.product_name ?? `${filament.material_type} ${filament.color_name}`}</h2><p>{filament.material_type}{filament.filler ? ` · ${filament.filler}` : ''}{filament.finish ? ` · ${filament.finish}` : ''}</p></div><dl className="catalog-meta"><div><dt>Color</dt><dd>{filament.color_name}</dd></div><div><dt>Diameter</dt><dd>{filament.diameter_mm} mm</dd></div><div><dt>Density</dt><dd>{filament.density_g_cm3} g/cm³</dd></div><div><dt>Nominal</dt><dd>{grams(filament.nominal_net_mass_g)}</dd></div></dl>{filament.material_template_revision_id && <p className="success-note">Template-linked profile ready to tune</p>}</Link>)}</section>}
    {showCreate ? <Modal title="Add a filament" description="Link the canonical product to a published template. It inherits that base and stores only later differences." onClose={() => setShowCreate(false)} size="wide" footer={<><button className="button" type="button" onClick={() => setShowCreate(false)}>Cancel</button><button className="button button--primary" form="create-filament" disabled={create.isPending || !publishedTemplates.length}><Plus size={17} />{create.isPending ? 'Creating…' : 'Create filament'}</button></>}>
      {publishedTemplates.length ? <form id="create-filament" className="editor-form" onSubmit={submit}>
        <EditorSection title="Product identity" description="Choose the starting profile and the labels operators see throughout inventory.">
          <div className="form-grid">
            <label>Starting template<select name="material_template_revision_id" required autoFocus>{publishedTemplates.map(({ template, revision }) => <option key={revision.id} value={revision.id}>{template.name} · {template.nozzle_diameter_mm} mm · v{revision.version}</option>)}</select></label>
            <label>Vendor<select name="vendor_id"><option value="">Unspecified vendor</option>{vendors.data?.map((vendor) => <option key={vendor.id} value={vendor.id}>{vendor.name}</option>)}</select></label>
            <label>Product name<input name="product_name" maxLength={160} placeholder="PolyLite PLA" /></label>
            <label>Color name<input list="filament-colors" value={colorName} onChange={(event) => { const name = event.target.value; setColorName(name); const normalized = name.normalize('NFKC').trim().toLocaleLowerCase(); const remembered = colors.data?.find((color) => color.normalized_name === normalized); if (remembered) setColorHex(`#${remembered.color_hex}`) }} maxLength={96} required /><datalist id="filament-colors">{colors.data?.map((color) => <option key={color.id} value={color.name} />)}</datalist></label>
            <label>Screen color sample<input type="color" value={colorHex} onChange={(event) => setColorHex(event.target.value.toUpperCase())} /><small className="field-help">Remembered for every matching color name.</small></label>
          </div>
        </EditorSection>
        <EditorSection title="Physical specifications" description="Record the diameter, density, packaged mass, and material modifiers.">
          <div className="form-grid">
            <label>Filament diameter (mm)<input name="diameter_mm" type="number" min="0.1" step="0.01" defaultValue="1.75" required /></label>
            <label>Diameter tolerance (mm)<input name="tolerance_mm" type="number" min="0" step="0.001" /></label>
            <label>Density (g/cm³)<input name="density_g_cm3" type="number" min="0.01" step="0.001" defaultValue="1.24" required /></label>
            <label>Nominal net mass (g)<input name="nominal_net_mass_g" type="number" min="1" step="0.1" defaultValue="1000" required /></label>
            <label>Filler<input name="filler" maxLength={96} placeholder="Carbon fiber, glass…" /></label>
            <label>Finish<input name="finish" maxLength={96} placeholder="Matte, silk…" /></label>
            <label className="form-grid__wide">Notes<textarea name="notes" rows={3} maxLength={4000} /></label>
          </div>
        </EditorSection>
        {create.error ? <p className="form-error" role="alert">{create.error.message}</p> : null}
      </form> : <p className="form-error">Publish at least one material template before adding filament products.</p>}
    </Modal> : null}
  </div>
}
