import { describe, expect, it } from 'vitest'
import type { BuildPlate, CuraSettingCatalogItem, MaterialSettings } from '../api/types'
import { getMaterialSettingDifferences, getScopeMismatchFields, normalizeDecimal } from './materialComparison'

const settings: MaterialSettings = {
  chamber_temp_c: null,
  extruder_temp_c: '210',
  bed_temp_c: '60',
  flow_percent: '100',
  print_speed_mm_s: '120',
  outer_wall_speed_mm_s: null,
  inner_wall_speed_mm_s: null,
  infill_speed_mm_s: null,
  top_bottom_speed_mm_s: null,
  initial_layer_speed_mm_s: null,
  travel_speed_mm_s: null,
  support_speed_mm_s: null,
  retraction_distance_mm: null,
  retraction_speed_mm_s: null,
  retraction_prime_speed_mm_s: null,
  cooling_enabled: true,
  cooling_min_percent: '30',
  cooling_max_percent: '100',
  support_overhang_angle_deg: null,
  tree_max_branch_angle_deg: null,
  pressure_advance: '0.035',
  filament_density_g_cm3: '1.24',
  preferred_build_plate_surface_id: 'surface-a',
  cura_extensions: { retraction_enable: true, xy_offset: '0.05' },
}

const catalog: CuraSettingCatalogItem[] = [
  { key: 'retraction_enable', label: 'Enable Retraction', value_type: 'boolean', unit: null, editable: true },
  { key: 'xy_offset', label: 'Horizontal Expansion', value_type: 'number', unit: 'mm', editable: true },
]

const plates = [{
  id: 'plate-id',
  plate_code: 'P1',
  display_name: 'Plate 1',
  description: null,
  manufacturer: null,
  product_name: null,
  shape: null,
  dimensions_mm: {},
  magnetic: null,
  flexible: null,
  condition: 'good',
  status: 'available',
  preferred_materials: [],
  max_bed_temp_c: null,
  last_cleaned_at: null,
  cleaning_due_after_prints: 10,
  cleaning_due_after_days: 7,
  mesh_due_after_prints: 30,
  mesh_due_after_days: 30,
    notes: null,
    image_url: null,
    image_version: 0,
    record_version: 1,
  surfaces: [{
    id: 'surface-a', build_plate_id: 'plate-id', side: 'a', surface_code: 'P1',
    klipper_mesh_profile: 'P1', surface_material: 'PEI', texture: 'smooth',
    mesh_available: true, last_mesh_checked_at: null, last_mesh_calibrated_at: null,
    notes: null, record_version: 1, completed_print_count: 0,
  }],
}] satisfies BuildPlate[]

describe('material comparison', () => {
  it('normalizes equivalent decimal formatting without floating-point conversion', () => {
    expect(normalizeDecimal('00210.000')).toBe('210')
    expect(normalizeDecimal('-0.000')).toBe('0')
    expect(normalizeDecimal('0.0350')).toBe('0.035')
  })

  it('returns only different core and Cura extension settings', () => {
    const other: MaterialSettings = {
      ...settings,
      extruder_temp_c: '215.0',
      flow_percent: '100.000',
      cooling_enabled: false,
      preferred_build_plate_surface_id: null,
      cura_extensions: { retraction_enable: false, xy_offset: '0.0500' },
    }

    expect(getMaterialSettingDifferences(settings, other, catalog, plates)).toEqual([
      { key: 'extruder_temp_c', label: 'Printing temperature', leftDisplay: '210 °C', rightDisplay: '215 °C' },
      { key: 'cooling_enabled', label: 'Print cooling', leftDisplay: 'Yes', rightDisplay: 'No' },
      { key: 'preferred_build_plate_surface_id', label: 'Preferred plate side', leftDisplay: 'P1 · PEI', rightDisplay: 'Not set' },
      { key: 'retraction_enable', label: 'Enable Retraction', leftDisplay: 'Yes', rightDisplay: 'No' },
    ])
  })

  it('allows different scopes while reporting the mismatched dimensions', () => {
    expect(getScopeMismatchFields(
      { printerId: 'printer-a', nozzleDiameterMm: '0.40' },
      { printerId: 'printer-b', nozzleDiameterMm: '0.6' },
    )).toEqual(['printer', 'nozzle diameter'])
    expect(getScopeMismatchFields(
      { printerId: 'printer-a', nozzleDiameterMm: '0.40' },
      { printerId: 'printer-a', nozzleDiameterMm: '0.400' },
    )).toEqual([])
  })
})
