import { compactNumber, titleCase } from './format'

/** Cura's internal keys stay unchanged; only their operator-facing names differ. */
export function calibrationSuggestionLabel(key: string): string {
  const curaKey = key.replace('cura_extensions.', '')
  if (curaKey === 'xy_offset') return 'Horizontal Expansion'
  if (curaKey === 'hole_xy_offset') return 'Hole Horizontal Expansion'
  return titleCase(curaKey.replaceAll('_', ' '))
}

/** Format review values without rounding or converting the settings sent to Cura. */
export function calibrationSuggestionValue(key: string, value: unknown): string {
  if (typeof value === 'boolean') return value ? 'Enabled' : 'Disabled'
  const text = String(value)
  const formatted = /^[-+]?\d+(?:\.\d+)?$/.test(text) ? compactNumber(text, 2) : text
  return ['xy_offset', 'hole_xy_offset'].includes(key.replace('cura_extensions.', '')) ? `${formatted} mm` : formatted
}

/** The recorded test plate is context, not a Cura setting or compatibility rating. */
export function visibleCalibrationSuggestions(suggestions: Record<string, unknown>) {
  return Object.entries(suggestions).filter(([key]) => key !== 'preferred_build_plate_surface_id')
}
