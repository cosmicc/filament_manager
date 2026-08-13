import type { BuildPlate, CuraSettingCatalogItem, MaterialSettings } from '../api/types'

export interface MaterialSettingDifference {
  key: string
  label: string
  leftDisplay: string
  rightDisplay: string
}

export interface MaterialScope {
  printerId: string
  nozzleDiameterMm: string
}

type ComparisonValueType = 'boolean' | 'number' | 'plate' | 'string'

const coreComparisonFields: Array<{
  key: Exclude<keyof MaterialSettings, 'cura_extensions'>
  label: string
  unit?: string
  valueType: ComparisonValueType
}> = [
  { key: 'extruder_temp_c', label: 'Printing temperature', unit: '°C', valueType: 'number' },
  { key: 'bed_temp_c', label: 'Build plate temperature', unit: '°C', valueType: 'number' },
  { key: 'chamber_temp_c', label: 'Chamber temperature', unit: '°C', valueType: 'number' },
  { key: 'flow_percent', label: 'Flow', unit: '%', valueType: 'number' },
  { key: 'print_speed_mm_s', label: 'Print speed', unit: 'mm/s', valueType: 'number' },
  { key: 'outer_wall_speed_mm_s', label: 'Outer wall speed', unit: 'mm/s', valueType: 'number' },
  { key: 'inner_wall_speed_mm_s', label: 'Inner wall speed', unit: 'mm/s', valueType: 'number' },
  { key: 'infill_speed_mm_s', label: 'Infill speed', unit: 'mm/s', valueType: 'number' },
  { key: 'top_bottom_speed_mm_s', label: 'Top/bottom speed', unit: 'mm/s', valueType: 'number' },
  { key: 'initial_layer_speed_mm_s', label: 'Initial layer speed', unit: 'mm/s', valueType: 'number' },
  { key: 'travel_speed_mm_s', label: 'Travel speed', unit: 'mm/s', valueType: 'number' },
  { key: 'support_speed_mm_s', label: 'Support speed', unit: 'mm/s', valueType: 'number' },
  { key: 'retraction_distance_mm', label: 'Retraction distance', unit: 'mm', valueType: 'number' },
  { key: 'retraction_speed_mm_s', label: 'Retraction speed', unit: 'mm/s', valueType: 'number' },
  { key: 'cooling_enabled', label: 'Print cooling', valueType: 'boolean' },
  { key: 'cooling_min_percent', label: 'Minimum fan', unit: '%', valueType: 'number' },
  { key: 'cooling_max_percent', label: 'Maximum fan', unit: '%', valueType: 'number' },
  { key: 'support_overhang_angle_deg', label: 'Support overhang angle', unit: '°', valueType: 'number' },
  { key: 'tree_max_branch_angle_deg', label: 'Tree maximum branch angle', unit: '°', valueType: 'number' },
  { key: 'pressure_advance', label: 'Klipper pressure advance', unit: 's', valueType: 'number' },
  { key: 'filament_density_g_cm3', label: 'Filament density', unit: 'g/cm³', valueType: 'number' },
  { key: 'preferred_build_plate_surface_id', label: 'Preferred plate side', valueType: 'plate' },
]

/** Normalize decimal text without binary floating-point conversion. */
export function normalizeDecimal(value: string | number): string {
  const raw = String(value).trim()
  const match = raw.match(/^([+-]?)(\d+)(?:\.(\d*))?$/)
  if (!match) return raw

  const integer = match[2].replace(/^0+(?=\d)/, '')
  const fraction = (match[3] ?? '').replace(/0+$/, '')
  const isZero = integer === '0' && fraction.length === 0
  const sign = match[1] === '-' && !isZero ? '-' : ''
  return `${sign}${integer}${fraction ? `.${fraction}` : ''}`
}

function isUnset(value: unknown): value is null | undefined | '' {
  return value === null || value === undefined || value === ''
}

function comparableValue(value: unknown, valueType: ComparisonValueType): string {
  if (isUnset(value)) return 'unset'
  if (valueType === 'number') return `number:${normalizeDecimal(String(value))}`
  if (valueType === 'boolean') return `boolean:${value === true || value === 'true'}`
  return `string:${String(value)}`
}

function displayValue(
  value: unknown,
  valueType: ComparisonValueType,
  unit: string | null | undefined,
  plateNames: Map<string, string>,
): string {
  if (isUnset(value)) return 'Not set'
  if (valueType === 'boolean') return value === true || value === 'true' ? 'Yes' : 'No'
  if (valueType === 'plate') return plateNames.get(String(value)) ?? 'Unknown plate side'
  return `${String(value)}${unit ? ` ${unit}` : ''}`
}

function inferredExtensionType(
  leftValue: unknown,
  rightValue: unknown,
  catalogItem: CuraSettingCatalogItem | undefined,
): ComparisonValueType {
  if (catalogItem) return catalogItem.value_type
  if (typeof leftValue === 'boolean' || typeof rightValue === 'boolean') return 'boolean'
  if (typeof leftValue === 'number' || typeof rightValue === 'number') return 'number'
  return 'string'
}

/** Return only canonical material settings whose values differ. */
export function getMaterialSettingDifferences(
  left: MaterialSettings,
  right: MaterialSettings,
  catalog: CuraSettingCatalogItem[],
  plates: BuildPlate[],
): MaterialSettingDifference[] {
  const plateNames = new Map(
    plates.flatMap((plate) => plate.surfaces.map((surface) => [
      surface.id,
      `${surface.surface_code} · ${surface.surface_material ?? 'Surface not specified'}`,
    ] as const)),
  )
  const differences: MaterialSettingDifference[] = []

  for (const field of coreComparisonFields) {
    const leftValue = left[field.key]
    const rightValue = right[field.key]
    if (comparableValue(leftValue, field.valueType) === comparableValue(rightValue, field.valueType)) continue
    differences.push({
      key: field.key,
      label: field.label,
      leftDisplay: displayValue(leftValue, field.valueType, field.unit, plateNames),
      rightDisplay: displayValue(rightValue, field.valueType, field.unit, plateNames),
    })
  }

  const catalogByKey = new Map(catalog.map((item) => [item.key, item]))
  const extensionKeys = new Set([
    ...Object.keys(left.cura_extensions),
    ...Object.keys(right.cura_extensions),
  ])
  const orderedExtensionKeys = [...extensionKeys].sort((a, b) => {
    const aIndex = catalog.findIndex((item) => item.key === a)
    const bIndex = catalog.findIndex((item) => item.key === b)
    if (aIndex === -1 && bIndex === -1) return a.localeCompare(b)
    if (aIndex === -1) return 1
    if (bIndex === -1) return -1
    return aIndex - bIndex
  })

  for (const key of orderedExtensionKeys) {
    const leftValue = left.cura_extensions[key]
    const rightValue = right.cura_extensions[key]
    const item = catalogByKey.get(key)
    const valueType = inferredExtensionType(leftValue, rightValue, item)
    if (comparableValue(leftValue, valueType) === comparableValue(rightValue, valueType)) continue
    differences.push({
      key,
      label: item?.label ?? key.replaceAll('_', ' '),
      leftDisplay: displayValue(leftValue, valueType, item?.unit, plateNames),
      rightDisplay: displayValue(rightValue, valueType, item?.unit, plateNames),
    })
  }

  return differences
}

/** Identify scope dimensions that differ while still allowing the comparison. */
export function getScopeMismatchFields(left: MaterialScope, right: MaterialScope): string[] {
  const mismatches: string[] = []
  if (left.printerId !== right.printerId) mismatches.push('printer')
  if (normalizeDecimal(left.nozzleDiameterMm) !== normalizeDecimal(right.nozzleDiameterMm)) mismatches.push('nozzle diameter')
  return mismatches
}
