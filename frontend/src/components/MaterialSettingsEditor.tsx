/* This editor intentionally exports its form serializer and canonical typed-key set. */
/* eslint-disable react-refresh/only-export-components */
import { useId, useState } from 'react'
import type { BuildPlate, CuraSettingCatalogItem, MaterialSettings } from '../api/types'
import { compactNumber, inputNumber } from '../lib/format'
import { EditorSection } from './EditorSection'

export const typedCuraKeys = new Set([
  'build_volume_temperature', 'cool_fan_enabled', 'cool_fan_speed',
  'cool_fan_speed_min', 'default_material_bed_temperature',
  'default_material_print_temperature', 'klipper_pressure_advance_factor',
  'material_bed_temperature', 'material_flow', 'material_print_temperature',
  'retraction_amount', 'retraction_prime_speed', 'retraction_retract_speed',
  'retraction_speed', 'speed_infill', 'speed_layer_0',
  'speed_print', 'speed_print_layer_0', 'speed_support', 'speed_topbottom',
  'speed_travel', 'speed_wall_0', 'speed_wall_x', 'support_angle',
  'cool_fan_speed_max',
])

const coreFields: Array<{
  key: keyof MaterialSettings
  label: string
  unit?: string
  required?: boolean
  defaultValue?: string
  precision?: number
}> = [
  { key: 'extruder_temp_c', label: 'Printing temperature', unit: '°C', required: true, precision: 0 },
  { key: 'bed_temp_c', label: 'Build plate temperature', unit: '°C', required: true, precision: 0 },
  { key: 'chamber_temp_c', label: 'Chamber temperature', unit: '°C', precision: 0 },
  { key: 'flow_percent', label: 'Flow', unit: '%', required: true, defaultValue: '100', precision: 0 },
  { key: 'print_speed_mm_s', label: 'Print speed', unit: 'mm/s', precision: 0 },
  { key: 'outer_wall_speed_mm_s', label: 'Outer wall speed', unit: 'mm/s', precision: 0 },
  { key: 'inner_wall_speed_mm_s', label: 'Inner wall speed', unit: 'mm/s', precision: 0 },
  { key: 'infill_speed_mm_s', label: 'Infill speed', unit: 'mm/s', precision: 0 },
  { key: 'top_bottom_speed_mm_s', label: 'Top/bottom speed', unit: 'mm/s', precision: 0 },
  { key: 'initial_layer_speed_mm_s', label: 'Initial layer speed', unit: 'mm/s', precision: 0 },
  { key: 'travel_speed_mm_s', label: 'Travel speed', unit: 'mm/s', precision: 0 },
  { key: 'support_speed_mm_s', label: 'Support speed', unit: 'mm/s', precision: 0 },
  { key: 'retraction_distance_mm', label: 'Retraction distance', unit: 'mm', precision: 1 },
  { key: 'retraction_speed_mm_s', label: 'Retraction speed', unit: 'mm/s', precision: 0 },
  { key: 'cooling_min_percent', label: 'Minimum fan', unit: '%', required: true, defaultValue: '0', precision: 0 },
  { key: 'cooling_max_percent', label: 'Maximum fan', unit: '%', required: true, defaultValue: '100', precision: 0 },
  { key: 'support_overhang_angle_deg', label: 'Support overhang angle', unit: '°', precision: 0 },
  { key: 'tree_max_branch_angle_deg', label: 'Tree maximum branch angle', unit: '°', precision: 0 },
  { key: 'pressure_advance', label: 'Klipper pressure advance', unit: 's', precision: 2 },
  { key: 'filament_density_g_cm3', label: 'Filament density', unit: 'g/cm³', required: true, defaultValue: '1.24', precision: 2 },
]

export const canonicalMaterialFieldCount = coreFields.length + 2

type MaterialSettingGroup =
  | 'temperature'
  | 'flow'
  | 'speed'
  | 'retraction'
  | 'cooling'
  | 'support'
  | 'dimensional'
  | 'filament'
  | 'klipper'
  | 'build_plate'

function curaSettingGroup(key: string): MaterialSettingGroup {
  if (key.includes('flow')) return 'flow'
  if (key.startsWith('speed_') || key.endsWith('_speed')) return 'speed'
  if (
    key.startsWith('retraction_')
    || key.startsWith('retract_')
    || key === 'limit_support_retractions'
  ) return 'retraction'
  if (key.startsWith('cool_')) return 'cooling'
  if (key.startsWith('support_') || key.startsWith('tree_')) return 'support'
  if (key.startsWith('xy_offset') || key.startsWith('hole_xy_offset')) return 'dimensional'
  if (key.startsWith('klipper_')) return 'klipper'
  if (key.includes('temperature')) return 'temperature'
  return 'filament'
}

function extensionPrecision(item: CuraSettingCatalogItem): number {
  if (item.unit === '%' || item.unit === '°C' || item.unit === 'mm/s' || item.unit === '°') return 0
  if (item.key.startsWith('xy_offset') || item.key.startsWith('hole_xy_offset')) return 2
  if (item.key.startsWith('klipper_')) return 2
  if (item.unit === 'mm' || item.unit === 's') return 1
  return 1
}

function nullable(value: FormDataEntryValue | null) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

function preservedNumericValue(
  form: HTMLFormElement,
  name: string,
  submitted: FormDataEntryValue | null,
): FormDataEntryValue | null {
  const control = form.elements.namedItem(name)
  if (
    control instanceof HTMLInputElement
    && control.dataset.changed !== 'true'
    && control.dataset.exactValue !== undefined
  ) return control.dataset.exactValue
  return submitted
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
      const fieldName = `cura__${item.key}`
      const value = nullable(item.value_type === 'number'
        ? preservedNumericValue(form, fieldName, data.get(fieldName))
        : data.get(fieldName))
      if (value !== null) extensions[item.key] = value
    }
  }
  return {
    chamber_temp_c: nullable(preservedNumericValue(form, 'chamber_temp_c', data.get('chamber_temp_c'))),
    extruder_temp_c: String(preservedNumericValue(form, 'extruder_temp_c', data.get('extruder_temp_c'))),
    bed_temp_c: String(preservedNumericValue(form, 'bed_temp_c', data.get('bed_temp_c'))),
    flow_percent: String(preservedNumericValue(form, 'flow_percent', data.get('flow_percent'))),
    print_speed_mm_s: nullable(preservedNumericValue(form, 'print_speed_mm_s', data.get('print_speed_mm_s'))),
    outer_wall_speed_mm_s: nullable(preservedNumericValue(form, 'outer_wall_speed_mm_s', data.get('outer_wall_speed_mm_s'))),
    inner_wall_speed_mm_s: nullable(preservedNumericValue(form, 'inner_wall_speed_mm_s', data.get('inner_wall_speed_mm_s'))),
    infill_speed_mm_s: nullable(preservedNumericValue(form, 'infill_speed_mm_s', data.get('infill_speed_mm_s'))),
    top_bottom_speed_mm_s: nullable(preservedNumericValue(form, 'top_bottom_speed_mm_s', data.get('top_bottom_speed_mm_s'))),
    initial_layer_speed_mm_s: nullable(preservedNumericValue(form, 'initial_layer_speed_mm_s', data.get('initial_layer_speed_mm_s'))),
    travel_speed_mm_s: nullable(preservedNumericValue(form, 'travel_speed_mm_s', data.get('travel_speed_mm_s'))),
    support_speed_mm_s: nullable(preservedNumericValue(form, 'support_speed_mm_s', data.get('support_speed_mm_s'))),
    retraction_distance_mm: nullable(preservedNumericValue(form, 'retraction_distance_mm', data.get('retraction_distance_mm'))),
    retraction_speed_mm_s: nullable(preservedNumericValue(form, 'retraction_speed_mm_s', data.get('retraction_speed_mm_s'))),
    cooling_enabled: data.get('cooling_enabled') === 'on',
    cooling_min_percent: String(preservedNumericValue(form, 'cooling_min_percent', data.get('cooling_min_percent'))),
    cooling_max_percent: String(preservedNumericValue(form, 'cooling_max_percent', data.get('cooling_max_percent'))),
    support_overhang_angle_deg: nullable(preservedNumericValue(form, 'support_overhang_angle_deg', data.get('support_overhang_angle_deg'))),
    tree_max_branch_angle_deg: nullable(preservedNumericValue(form, 'tree_max_branch_angle_deg', data.get('tree_max_branch_angle_deg'))),
    pressure_advance: nullable(preservedNumericValue(form, 'pressure_advance', data.get('pressure_advance'))),
    filament_density_g_cm3: String(preservedNumericValue(form, 'filament_density_g_cm3', data.get('filament_density_g_cm3'))),
    preferred_build_plate_surface_id: nullable(data.get('preferred_build_plate_surface_id')),
    cura_extensions: extensions,
  }
}

export function MaterialSettingsEditor({
  settings,
  baseSettings,
  overrideKeys = [],
  validationErrors = {},
  catalog,
  plates,
}: {
  settings?: MaterialSettings
  baseSettings?: MaterialSettings | null
  overrideKeys?: string[]
  validationErrors?: Record<string, string[]>
  catalog: CuraSettingCatalogItem[]
  plates: BuildPlate[]
}) {
  const editorId = useId().replaceAll(':', '')
  const [resetKeys, setResetKeys] = useState<Set<string>>(() => new Set())
  const [liveOwnership, setLiveOwnership] = useState<Map<string, boolean>>(() => new Map())
  const customized = (key: string) => liveOwnership.get(key) ?? (overrideKeys.includes(key) && !resetKeys.has(key))
  const effectiveValue = (key: keyof MaterialSettings) => settings?.[key] ?? baseSettings?.[key]
  const effectiveExtensionValue = (key: string) => settings?.cura_extensions[key] ?? baseSettings?.cura_extensions[key]
  const extensionCatalog = catalog.filter((item) => item.editable && !typedCuraKeys.has(item.key))
  const errorsFor = (key: string) => validationErrors[key] ?? []
  const extensionErrorsFor = (key: string) => validationErrors[`cura_extensions.${key}`] ?? []
  const errorId = (key: string) => `${editorId}-${key.replaceAll(/[^a-zA-Z0-9_-]/g, '-')}-error`
  const fieldErrors = (key: string, messages = errorsFor(key)) => messages.length ? (
    <div className="field-validation" id={errorId(key)} role="alert">
      {messages.map((message) => <span key={message}>{message}</span>)}
    </div>
  ) : null
  const equivalent = (value: string | number | boolean | null | undefined, baseValue: string | number | boolean | null | undefined) => {
    if ((value == null || value === '') && (baseValue == null || baseValue === '')) return true
    if (typeof value === 'boolean' || typeof baseValue === 'boolean') return Boolean(value) === Boolean(baseValue)
    const numeric = Number(value)
    const baseNumeric = Number(baseValue)
    if (Number.isFinite(numeric) && Number.isFinite(baseNumeric)) return numeric === baseNumeric
    return String(value ?? '') === String(baseValue ?? '')
  }
  const markOwnership = (key: string, value: string | boolean, baseValue: string | number | boolean | null | undefined) => {
    if (!baseSettings) return
    setLiveOwnership((current) => new Map(current).set(key, !equivalent(value, baseValue)))
  }
  const displayedBaseValue = (key: string, value: string | number | boolean | null | undefined) => {
    if (value == null || value === '') return 'Not set'
    if (typeof value === 'boolean') return value ? 'Enabled' : 'Disabled'
    const coreField = coreFields.find((field) => field.key === key)
    const extension = extensionCatalog.find((item) => item.key === key)
    return compactNumber(value, coreField?.precision ?? (extension ? extensionPrecision(extension) : 1))
  }
  const resetControl = (
    key: string,
    baseValue: string | number | boolean | null | undefined,
    button: HTMLButtonElement,
  ) => {
    const field = button.closest('.setting-field')
    const control = field?.querySelector('input, select')
    if (control instanceof HTMLInputElement && control.type === 'checkbox') {
      control.checked = Boolean(baseValue)
    } else if (control instanceof HTMLInputElement || control instanceof HTMLSelectElement) {
      const coreField = coreFields.find((item) => item.key === key)
      const extension = extensionCatalog.find((item) => item.key === key)
      control.value = baseValue == null
        ? ''
        : control instanceof HTMLInputElement && control.type === 'number'
          ? inputNumber(baseValue as string | number, coreField?.precision ?? (extension ? extensionPrecision(extension) : 1))
          : String(baseValue)
      if (control instanceof HTMLInputElement && control.type === 'number') {
        control.dataset.exactValue = baseValue == null ? '' : String(baseValue)
        delete control.dataset.changed
      }
    }
    setResetKeys((current) => new Set(current).add(key))
    setLiveOwnership((current) => new Map(current).set(key, false))
  }
  const ownership = (
    key: string,
    baseValue: string | number | boolean | null | undefined,
  ) => baseSettings ? (
    <div className="setting-ownership">
      <span>{customized(key) ? 'Customized' : 'Inherited'} · Template: {displayedBaseValue(key, baseValue)}</span>
      {customized(key) ? <button className="button button--small" type="button" onClick={(event) => resetControl(key, baseValue, event.currentTarget)}>Reset to Template</button> : null}
    </div>
  ) : null
  const fieldGroups: Array<{
    id: MaterialSettingGroup
    title: string
    description: string
    keys: Array<keyof MaterialSettings>
  }> = [
    {
      id: 'temperature',
      title: 'Temperatures',
      description: 'Nozzle, build plate, chamber, standby, initial, and final material temperatures.',
      keys: ['extruder_temp_c', 'bed_temp_c', 'chamber_temp_c'],
    },
    {
      id: 'flow',
      title: 'Flow',
      description: 'Overall and feature-specific material flow percentages.',
      keys: ['flow_percent'],
    },
    {
      id: 'speed',
      title: 'Speeds',
      description: 'Print, wall, infill, travel, support, first-layer, and feature speeds.',
      keys: ['print_speed_mm_s', 'outer_wall_speed_mm_s', 'inner_wall_speed_mm_s', 'infill_speed_mm_s', 'top_bottom_speed_mm_s', 'initial_layer_speed_mm_s', 'travel_speed_mm_s', 'support_speed_mm_s'],
    },
    {
      id: 'retraction',
      title: 'Retraction',
      description: 'Retraction distance, speeds, travel limits, and layer-change behavior.',
      keys: ['retraction_distance_mm', 'retraction_speed_mm_s'],
    },
    {
      id: 'cooling',
      title: 'Cooling',
      description: 'Fan behavior and minimum-layer cooling controls.',
      keys: ['cooling_min_percent', 'cooling_max_percent'],
    },
    {
      id: 'support',
      title: 'Support',
      description: 'Support overhang and tree-support behavior.',
      keys: ['support_overhang_angle_deg', 'tree_max_branch_angle_deg'],
    },
    {
      id: 'dimensional',
      title: 'Dimensional compensation',
      description: 'Horizontal, hole, and first-layer dimensional adjustments.',
      keys: [],
    },
    {
      id: 'filament',
      title: 'Filament properties',
      description: 'Physical material values used for calculations and Cura output.',
      keys: ['filament_density_g_cm3'],
    },
    {
      id: 'klipper',
      title: 'Klipper',
      description: 'Pressure advance and smooth-time controls owned by the Klipper settings integration.',
      keys: ['pressure_advance'],
    },
    {
      id: 'build_plate',
      title: 'Build plate',
      description: 'The preferred printable surface for this material.',
      keys: [],
    },
  ]
  return (
    <div className="editor-form">
      {fieldGroups.map((group) => (
        <EditorSection key={group.title} title={group.title} description={group.description}>
          <div className="form-grid">
            {coreFields.filter((field) => group.keys.includes(field.key)).map((field) => (
              <div className={`setting-field${customized(field.key) ? ' setting-field--customized' : ''}${errorsFor(field.key).length ? ' setting-field--invalid' : ''}`} key={field.key}>
                <label>
                  {field.label}{field.unit ? ` (${field.unit})` : ''}
                  <input
                    name={field.key}
                    type="number"
                    step={field.precision === 0 ? '1' : field.precision === 1 ? '0.1' : '0.01'}
                    min={field.key === 'pressure_advance' ? '0' : undefined}
                    required={field.required}
                    defaultValue={effectiveValue(field.key) == null ? field.defaultValue ?? '' : inputNumber(effectiveValue(field.key) as string | number | null, field.precision)}
                    data-exact-value={effectiveValue(field.key) == null ? field.defaultValue ?? '' : String(effectiveValue(field.key))}
                    aria-invalid={errorsFor(field.key).length ? true : undefined}
                    aria-describedby={errorsFor(field.key).length ? errorId(field.key) : undefined}
                    onChange={(event) => { event.currentTarget.dataset.changed = 'true'; markOwnership(field.key, event.currentTarget.value, baseSettings?.[field.key] as string | number | boolean | null | undefined) }}
                  />
                </label>
                {fieldErrors(field.key)}
                {ownership(field.key, baseSettings?.[field.key] as string | number | boolean | null | undefined)}
              </div>
            ))}
            {group.id === 'cooling' ? (
              <div className={`setting-field${customized('cooling_enabled') ? ' setting-field--customized' : ''}${errorsFor('cooling_enabled').length ? ' setting-field--invalid' : ''}`}>
                <label className="check-row">
                  <input name="cooling_enabled" type="checkbox" defaultChecked={effectiveValue('cooling_enabled') == null ? true : Boolean(effectiveValue('cooling_enabled'))} aria-invalid={errorsFor('cooling_enabled').length ? true : undefined} aria-describedby={errorsFor('cooling_enabled').length ? errorId('cooling_enabled') : undefined} onChange={(event) => markOwnership('cooling_enabled', event.currentTarget.checked, baseSettings?.cooling_enabled)} />
                  <span><strong>Enable print cooling</strong><small>Stored with the current material settings.</small></span>
                </label>
                {fieldErrors('cooling_enabled')}
                {ownership('cooling_enabled', baseSettings?.cooling_enabled)}
              </div>
            ) : null}
            {extensionCatalog.filter((item) => curaSettingGroup(item.key) === group.id).map((item) => (
              <div className={`setting-field${customized(item.key) ? ' setting-field--customized' : ''}${extensionErrorsFor(item.key).length ? ' setting-field--invalid' : ''}`} key={item.key}>
                {item.value_type === 'boolean' ? (
                  <label className="check-row">
                    <input name={`cura__${item.key}`} type="checkbox" defaultChecked={Boolean(effectiveExtensionValue(item.key))} aria-invalid={extensionErrorsFor(item.key).length ? true : undefined} aria-describedby={extensionErrorsFor(item.key).length ? errorId(`cura_extensions.${item.key}`) : undefined} onChange={(event) => markOwnership(item.key, event.currentTarget.checked, baseSettings?.cura_extensions[item.key])} />
                    <span><strong>{item.label}</strong><small>{item.key}</small></span>
                  </label>
                ) : (
                  <label>
                    {item.label}{item.unit ? ` (${item.unit})` : ''}
                    <input
                      name={`cura__${item.key}`}
                      type={item.value_type === 'number' ? 'number' : 'text'}
                      step={item.value_type === 'number' ? 10 ** -extensionPrecision(item) : undefined}
                      defaultValue={effectiveExtensionValue(item.key) == null ? '' : item.value_type === 'number' ? inputNumber(effectiveExtensionValue(item.key) as string | number, extensionPrecision(item)) : String(effectiveExtensionValue(item.key))}
                      data-exact-value={item.value_type === 'number' ? String(effectiveExtensionValue(item.key) ?? '') : undefined}
                      aria-invalid={extensionErrorsFor(item.key).length ? true : undefined}
                      aria-describedby={extensionErrorsFor(item.key).length ? errorId(`cura_extensions.${item.key}`) : undefined}
                      onChange={(event) => { if (item.value_type === 'number') event.currentTarget.dataset.changed = 'true'; markOwnership(item.key, event.currentTarget.value, baseSettings?.cura_extensions[item.key]) }}
                    />
                    <small className="field-help">{item.key}</small>
                  </label>
                )}
                {fieldErrors(`cura_extensions.${item.key}`, extensionErrorsFor(item.key))}
                {ownership(item.key, baseSettings?.cura_extensions[item.key])}
              </div>
            ))}
            {group.id === 'build_plate' ? (
              <div className={`setting-field${customized('preferred_build_plate_surface_id') ? ' setting-field--customized' : ''}${errorsFor('preferred_build_plate_surface_id').length ? ' setting-field--invalid' : ''}`}>
                <label>
                  Preferred plate side
                  <select name="preferred_build_plate_surface_id" defaultValue={String(effectiveValue('preferred_build_plate_surface_id') ?? '')} aria-invalid={errorsFor('preferred_build_plate_surface_id').length ? true : undefined} aria-describedby={errorsFor('preferred_build_plate_surface_id').length ? errorId('preferred_build_plate_surface_id') : undefined} onChange={(event) => markOwnership('preferred_build_plate_surface_id', event.currentTarget.value, baseSettings?.preferred_build_plate_surface_id)}>
                    <option value="">No preference</option>
                    {plates.flatMap((plate) => plate.surfaces.map((surface) => (
                      <option key={surface.id} value={surface.id}>
                        {surface.surface_code} · {surface.surface_material ?? 'Surface not specified'} · {surface.texture ?? 'texture not specified'}
                      </option>
                    )))}
                  </select>
                </label>
                {fieldErrors('preferred_build_plate_surface_id')}
                {ownership('preferred_build_plate_surface_id', baseSettings?.preferred_build_plate_surface_id)}
              </div>
            ) : null}
          </div>
        </EditorSection>
      ))}
    </div>
  )
}
