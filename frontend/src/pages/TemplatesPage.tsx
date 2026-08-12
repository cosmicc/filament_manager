import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CopyPlus, Library, Plus, Upload } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { apiFetch } from '../api/client'
import type {
  BuildPlate,
  CuraSettingCatalogItem,
  MaterialSettings,
  MaterialTemplate,
  Printer,
} from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'

const typedCuraKeys = new Set([
  'build_volume_temperature', 'cool_fan_enabled', 'cool_fan_speed',
  'cool_fan_speed_min', 'default_material_bed_temperature',
  'default_material_print_temperature', 'klipper_pressure_advance_factor',
  'material_bed_temperature', 'material_flow', 'material_print_temperature',
  'retraction_amount', 'retraction_speed', 'speed_infill', 'speed_layer_0',
  'speed_print', 'speed_print_layer_0', 'speed_support', 'speed_topbottom',
  'speed_travel', 'speed_wall_0', 'speed_wall_x', 'support_angle',
])

const coreFields: Array<{ key: keyof MaterialSettings; label: string; unit?: string; required?: boolean; defaultValue?: string }> = [
  { key: 'extruder_temp_c', label: 'Printing temperature', unit: '°C', required: true },
  { key: 'bed_temp_c', label: 'Build plate temperature', unit: '°C', required: true },
  { key: 'chamber_temp_c', label: 'Chamber temperature', unit: '°C' },
  { key: 'flow_percent', label: 'Flow', unit: '%', required: true, defaultValue: '100' },
  { key: 'print_speed_mm_s', label: 'Print speed', unit: 'mm/s' },
  { key: 'outer_wall_speed_mm_s', label: 'Outer wall speed', unit: 'mm/s' },
  { key: 'inner_wall_speed_mm_s', label: 'Inner wall speed', unit: 'mm/s' },
  { key: 'infill_speed_mm_s', label: 'Infill speed', unit: 'mm/s' },
  { key: 'top_bottom_speed_mm_s', label: 'Top/bottom speed', unit: 'mm/s' },
  { key: 'initial_layer_speed_mm_s', label: 'Initial layer speed', unit: 'mm/s' },
  { key: 'travel_speed_mm_s', label: 'Travel speed', unit: 'mm/s' },
  { key: 'support_speed_mm_s', label: 'Support speed', unit: 'mm/s' },
  { key: 'retraction_distance_mm', label: 'Retraction distance', unit: 'mm' },
  { key: 'retraction_speed_mm_s', label: 'Retraction speed', unit: 'mm/s' },
  { key: 'cooling_min_percent', label: 'Minimum fan', unit: '%', required: true, defaultValue: '0' },
  { key: 'cooling_max_percent', label: 'Maximum fan', unit: '%', required: true, defaultValue: '100' },
  { key: 'support_overhang_angle_deg', label: 'Support overhang angle', unit: '°' },
  { key: 'tree_max_branch_angle_deg', label: 'Tree maximum branch angle', unit: '°' },
  { key: 'pressure_advance', label: 'Klipper pressure advance', unit: 's' },
  { key: 'filament_density_g_cm3', label: 'Generic density', unit: 'g/cm³', required: true, defaultValue: '1.24' },
]

function nullable(value: FormDataEntryValue | null) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

function settingsFromForm(form: HTMLFormElement, catalog: CuraSettingCatalogItem[]): MaterialSettings {
  const data = new FormData(form)
  const extensions: Record<string, string | boolean> = {}
  for (const item of catalog) {
    if (!item.editable || typedCuraKeys.has(item.key)) continue
    if (item.value_type === 'boolean') extensions[item.key] = data.get(`cura__${item.key}`) === 'on'
    else {
      const value = nullable(data.get(`cura__${item.key}`))
      if (value !== null) extensions[item.key] = value
    }
  }
  return {
    chamber_temp_c: nullable(data.get('chamber_temp_c')),
    extruder_temp_c: String(data.get('extruder_temp_c')),
    bed_temp_c: String(data.get('bed_temp_c')),
    flow_percent: String(data.get('flow_percent')),
    print_speed_mm_s: nullable(data.get('print_speed_mm_s')),
    outer_wall_speed_mm_s: nullable(data.get('outer_wall_speed_mm_s')),
    inner_wall_speed_mm_s: nullable(data.get('inner_wall_speed_mm_s')),
    infill_speed_mm_s: nullable(data.get('infill_speed_mm_s')),
    top_bottom_speed_mm_s: nullable(data.get('top_bottom_speed_mm_s')),
    initial_layer_speed_mm_s: nullable(data.get('initial_layer_speed_mm_s')),
    travel_speed_mm_s: nullable(data.get('travel_speed_mm_s')),
    support_speed_mm_s: nullable(data.get('support_speed_mm_s')),
    retraction_distance_mm: nullable(data.get('retraction_distance_mm')),
    retraction_speed_mm_s: nullable(data.get('retraction_speed_mm_s')),
    cooling_enabled: data.get('cooling_enabled') === 'on',
    cooling_min_percent: String(data.get('cooling_min_percent')),
    cooling_max_percent: String(data.get('cooling_max_percent')),
    support_overhang_angle_deg: nullable(data.get('support_overhang_angle_deg')),
    tree_max_branch_angle_deg: nullable(data.get('tree_max_branch_angle_deg')),
    pressure_advance: nullable(data.get('pressure_advance')),
    filament_density_g_cm3: String(data.get('filament_density_g_cm3')),
    preferred_build_plate_surface_id: nullable(data.get('preferred_build_plate_surface_id')),
    cura_extensions: extensions,
  }
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
  const extensionCatalog = (catalog.data ?? []).filter((item) => item.editable && !typedCuraKeys.has(item.key))
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
    <PageHeader eyebrow="Reusable starting points" title="Material templates" description="Create printer- and nozzle-specific generic materials. New filament products copy a published revision and can then be tuned independently." actions={user?.role !== 'viewer' ? <button className="button button--primary" onClick={() => { setRevisionSource(null); setShowEditor((value) => !value); setMessage('') }}><Plus size={17} /> Add template</button> : undefined} />
    {message && <div className="deployment-note" role="status">{message}</div>}
    {showEditor && <section className="card template-editor">
      <header className="card__header"><div><p className="eyebrow">{revisionSource ? `New ${revisionSource.name} revision` : 'New generic material'}</p><h2>{revisionSource ? 'Copy and adjust settings' : 'Template identity and settings'}</h2></div><Library size={21} /></header>
      <form className="form-stack" onSubmit={submit} key={revisionSource?.revisions[0]?.id ?? 'new-template'}>
        {!revisionSource && <div className="form-grid">
          <label>Template name<input name="name" placeholder="Generic PLA" required /></label>
          <label>Material type<input name="material_type" placeholder="PLA, PCTPE, Nylon 645…" required /></label>
          <label>Printer<select name="printer_id" required>{printers.data?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label>
          <label>Nozzle diameter<input name="nozzle_diameter_mm" type="number" min="0.1" step="0.05" defaultValue={printers.data?.[0]?.nozzle_diameter_mm ?? '0.4'} required /></label>
          <label>Filament diameter<input name="filament_diameter_mm" type="number" min="0.1" step="0.01" defaultValue="1.75" required /></label>
          <label className="form-grid__wide">Description<textarea name="description" rows={2} placeholder="Purpose, behavior, and calibration notes" /></label>
        </div>}
        <div className="form-grid">
          {coreFields.map((field) => <label key={field.key}>{field.label}{field.unit ? ` (${field.unit})` : ''}<input name={field.key} type="number" step="any" min={field.key === 'pressure_advance' ? '0' : undefined} required={field.required} defaultValue={sourceSettings?.[field.key] == null ? field.defaultValue ?? '' : String(sourceSettings[field.key])} /></label>)}
          <label>Preferred plate side<select name="preferred_build_plate_surface_id" defaultValue={sourceSettings?.preferred_build_plate_surface_id ?? ''}><option value="">No preference</option>{plates.data?.flatMap((plate) => plate.surfaces.map((surface) => <option key={surface.id} value={surface.id}>{surface.surface_code} · {surface.surface_material ?? 'Surface not specified'} · {surface.texture ?? 'texture not specified'}</option>))}</select></label>
          <label className="check-row"><input name="cooling_enabled" type="checkbox" defaultChecked={sourceSettings?.cooling_enabled ?? true} /><span><strong>Enable print cooling</strong><small>Stored with this material revision.</small></span></label>
        </div>
        <details className="advanced-settings"><summary>All additional Cura Material Settings ({extensionCatalog.length})</summary><div className="form-grid">{extensionCatalog.map((item) => item.value_type === 'boolean' ? <label className="check-row" key={item.key}><input name={`cura__${item.key}`} type="checkbox" defaultChecked={Boolean(sourceSettings?.cura_extensions[item.key])} /><span><strong>{item.label}</strong><small>{item.key}</small></span></label> : <label key={item.key}>{item.label}{item.unit ? ` (${item.unit})` : ''}<input name={`cura__${item.key}`} type={item.value_type === 'number' ? 'number' : 'text'} step={item.value_type === 'number' ? 'any' : undefined} defaultValue={sourceSettings?.cura_extensions[item.key] == null ? '' : String(sourceSettings.cura_extensions[item.key])} /><small className="field-help">{item.key}</small></label>)}</div></details>
        <div className="form-actions"><button type="button" className="button" onClick={() => { setShowEditor(false); setRevisionSource(null) }}>Cancel</button><button type="submit" className="button button--primary" disabled={save.isPending}>{revisionSource ? <CopyPlus size={17} /> : <Plus size={17} />}{save.isPending ? 'Saving…' : revisionSource ? 'Save new revision' : 'Save template'}</button></div>
      </form>
    </section>}
    {loading ? <LoadingState /> : !templates.data?.length ? <EmptyState icon={Library} title="No material templates" description="Add Generic PLA, PETG, ASA, PLA+, TPU, PCTPE, Nylon 645, and any other starting materials you use." /> : <div className="catalog-grid">{templates.data.map((template) => {
      const latest = template.revisions[0]
      return <article className="catalog-card catalog-card--template" key={template.id}><div><p className="eyebrow">{template.material_type} · {template.nozzle_diameter_mm} mm nozzle</p><h2>{template.name}</h2><p>{template.description ?? 'No description'}</p></div><dl className="catalog-meta"><div><dt>Printer</dt><dd>{printers.data?.find((item) => item.id === template.printer_id)?.name ?? 'Unknown'}</dd></div><div><dt>Revision</dt><dd>v{latest.version}</dd></div><div><dt>Temperatures</dt><dd>{latest.settings.extruder_temp_c}° / {latest.settings.bed_temp_c}°</dd></div><div><dt>Cura settings</dt><dd>{Object.keys(latest.settings.cura_extensions).length + typedCuraKeys.size} available</dd></div></dl><div className="template-card__actions"><StatusPill status={latest.status} />{user?.role !== 'viewer' && latest.status !== 'published' && <button className="button button--primary" disabled={publish.isPending} onClick={() => publish.mutate({ templateId: template.id, revisionId: latest.id })}><Upload size={16} /> Publish v{latest.version}</button>}{user?.role !== 'viewer' && <button className="button" onClick={() => openNewRevision(template)}><CopyPlus size={16} /> New revision</button>}</div></article>
    })}</div>}
  </div>
}
