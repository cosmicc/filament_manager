/* This editor intentionally exports its form serializer and canonical typed-key set. */
/* eslint-disable react-refresh/only-export-components */
import type { BuildPlate, CuraSettingCatalogItem, MaterialSettings } from '../api/types'
import { EditorSection } from './EditorSection'

export const typedCuraKeys = new Set([
  'build_volume_temperature', 'cool_fan_enabled', 'cool_fan_speed',
  'cool_fan_speed_min', 'default_material_bed_temperature',
  'default_material_print_temperature', 'klipper_pressure_advance_factor',
  'material_bed_temperature', 'material_flow', 'material_print_temperature',
  'retraction_amount', 'retraction_speed', 'speed_infill', 'speed_layer_0',
  'speed_print', 'speed_print_layer_0', 'speed_support', 'speed_topbottom',
  'speed_travel', 'speed_wall_0', 'speed_wall_x', 'support_angle',
])

const coreFields: Array<{
  key: keyof MaterialSettings
  label: string
  unit?: string
  required?: boolean
  defaultValue?: string
}> = [
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
  { key: 'filament_density_g_cm3', label: 'Filament density', unit: 'g/cm³', required: true, defaultValue: '1.24' },
]

function nullable(value: FormDataEntryValue | null) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

export function settingsFromForm(
  form: HTMLFormElement,
  catalog: CuraSettingCatalogItem[],
): MaterialSettings {
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

export function MaterialSettingsEditor({
  settings,
  catalog,
  plates,
}: {
  settings?: MaterialSettings
  catalog: CuraSettingCatalogItem[]
  plates: BuildPlate[]
}) {
  const extensionCatalog = catalog.filter((item) => item.editable && !typedCuraKeys.has(item.key))
  const fieldGroups = [
    {
      title: 'Temperature, flow, and filament',
      description: 'Core material values used for every generated Cura profile.',
      keys: ['extruder_temp_c', 'bed_temp_c', 'chamber_temp_c', 'flow_percent', 'filament_density_g_cm3'],
    },
    {
      title: 'Print speeds',
      description: 'Optional speed limits for walls, infill, travel, support, and the first layer.',
      keys: ['print_speed_mm_s', 'outer_wall_speed_mm_s', 'inner_wall_speed_mm_s', 'infill_speed_mm_s', 'top_bottom_speed_mm_s', 'initial_layer_speed_mm_s', 'travel_speed_mm_s', 'support_speed_mm_s'],
    },
    {
      title: 'Retraction, cooling, and support',
      description: 'Material handling values that affect stringing, cooling, and overhang behavior.',
      keys: ['retraction_distance_mm', 'retraction_speed_mm_s', 'cooling_min_percent', 'cooling_max_percent', 'support_overhang_angle_deg', 'tree_max_branch_angle_deg'],
    },
    {
      title: 'Klipper and build plate',
      description: 'Printer-specific pressure advance and the preferred printable surface.',
      keys: ['pressure_advance'],
    },
  ]
  return (
    <div className="editor-form">
      {fieldGroups.map((group) => (
        <EditorSection key={group.title} title={group.title} description={group.description}>
          <div className="form-grid">
            {coreFields.filter((field) => group.keys.includes(field.key)).map((field) => (
              <label key={field.key}>
                {field.label}{field.unit ? ` (${field.unit})` : ''}
                <input
                  name={field.key}
                  type="number"
                  step="any"
                  min={field.key === 'pressure_advance' ? '0' : undefined}
                  required={field.required}
                  defaultValue={settings?.[field.key] == null ? field.defaultValue ?? '' : String(settings[field.key])}
                />
              </label>
            ))}
            {group.title === 'Retraction, cooling, and support' ? (
              <label className="check-row">
                <input name="cooling_enabled" type="checkbox" defaultChecked={settings?.cooling_enabled ?? true} />
                <span><strong>Enable print cooling</strong><small>Stored with this material revision.</small></span>
              </label>
            ) : null}
            {group.title === 'Klipper and build plate' ? (
              <label>
                Preferred plate side
                <select name="preferred_build_plate_surface_id" defaultValue={settings?.preferred_build_plate_surface_id ?? ''}>
                  <option value="">No preference</option>
                  {plates.flatMap((plate) => plate.surfaces.map((surface) => (
                    <option key={surface.id} value={surface.id}>
                      {surface.surface_code} · {surface.surface_material ?? 'Surface not specified'} · {surface.texture ?? 'texture not specified'}
                    </option>
                  )))}
                </select>
              </label>
            ) : null}
          </div>
        </EditorSection>
      ))}
      <EditorSection title={`Additional Cura Material Settings (${extensionCatalog.length})`} description="All supported advanced values remain visible and grouped instead of hidden behind a fold-down section.">
        {extensionCatalog.length ? (
          <div className="form-grid">
            {extensionCatalog.map((item) => item.value_type === 'boolean' ? (
              <label className="check-row" key={item.key}>
                <input name={`cura__${item.key}`} type="checkbox" defaultChecked={Boolean(settings?.cura_extensions[item.key])} />
                <span><strong>{item.label}</strong><small>{item.key}</small></span>
              </label>
            ) : (
              <label key={item.key}>
                {item.label}{item.unit ? ` (${item.unit})` : ''}
                <input
                  name={`cura__${item.key}`}
                  type={item.value_type === 'number' ? 'number' : 'text'}
                  step={item.value_type === 'number' ? 'any' : undefined}
                  defaultValue={settings?.cura_extensions[item.key] == null ? '' : String(settings.cura_extensions[item.key])}
                />
                <small className="field-help">{item.key}</small>
              </label>
            ))}
          </div>
        ) : <p className="muted">No additional editable settings were reported.</p>}
      </EditorSection>
    </div>
  )
}
