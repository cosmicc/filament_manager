import { describe, expect, it } from 'vitest'
import { calibrationSuggestionLabel, calibrationSuggestionValue, visibleCalibrationSuggestions } from './calibrationSuggestions'

describe('calibration review presentation', () => {
  it('uses Cura labels and millimeters while preserving sign and limiting displayed precision', () => {
    expect(calibrationSuggestionLabel('cura_extensions.xy_offset')).toBe('Horizontal Expansion')
    expect(calibrationSuggestionLabel('cura_extensions.hole_xy_offset')).toBe('Hole Horizontal Expansion')
    expect(calibrationSuggestionValue('cura_extensions.xy_offset', '-0.125')).toBe('-0.13 mm')
    expect(calibrationSuggestionValue('cura_extensions.hole_xy_offset', '0.2000')).toBe('0.2 mm')
    expect(calibrationSuggestionValue('flow_percent', '95.238095')).toBe('95.24')
    expect(calibrationSuggestionValue('cooling_enabled', false)).toBe('Disabled')
  })

  it('hides retired plate preferences without mutating stored values', () => {
    const suggestions = { preferred_build_plate_surface_id: 'plate-side', 'cura_extensions.xy_offset': '0.075' }
    expect(visibleCalibrationSuggestions(suggestions)).toEqual([['cura_extensions.xy_offset', '0.075']])
    expect(suggestions.preferred_build_plate_surface_id).toBe('plate-side')
  })
})
