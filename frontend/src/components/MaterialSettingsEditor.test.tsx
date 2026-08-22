// @vitest-environment jsdom

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { MaterialSettings } from '../api/types'
import { MaterialSettingsEditor } from './MaterialSettingsEditor'

const settings: MaterialSettings = {
  chamber_temp_c: null,
  extruder_temp_c: '210',
  bed_temp_c: '60',
  flow_percent: '98',
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
  pressure_advance: null,
  filament_density_g_cm3: '1.24',
  preferred_build_plate_surface_id: null,
  cura_extensions: {},
}

describe('MaterialSettingsEditor validation', () => {
  it('shows an accessible red error beside the exact invalid value', () => {
    render(
      <MaterialSettingsEditor
        catalog={[]}
        plates={[]}
        validationErrors={{ flow_percent: ['Input should be greater than 0'] }}
      />,
    )

    const flow = screen.getByLabelText('Flow (%)')
    const message = screen.getByText('Input should be greater than 0')
    expect(flow.getAttribute('aria-invalid')).toBe('true')
    expect(flow.getAttribute('aria-describedby')).toBe(message.parentElement?.id)
    expect(message.parentElement?.className).toContain('field-validation')
  })

  it('groups every requested Cura cooling control and hides initial fan speed', () => {
    const rendered = render(
      <MaterialSettingsEditor
        plates={[]}
        catalog={[
          { key: 'cool_fan_full_layer', label: 'Regular Fan Speed at Layer', value_type: 'number', unit: null, editable: true },
          { key: 'cool_min_layer_time', label: 'Minimum Layer Time', value_type: 'number', unit: 's', editable: true },
          { key: 'cool_min_speed', label: 'Minimum Speed', value_type: 'number', unit: 'mm/s', editable: true },
          { key: 'cool_fan_speed_0', label: 'Initial Fan Speed', value_type: 'number', unit: '%', editable: false },
        ]}
      />,
    )

    const cooling = within(rendered.container).getByRole('heading', { name: 'Cooling' }).closest('section')
    expect(cooling).not.toBeNull()
    const controls = within(cooling as HTMLElement)
    expect(controls.getByLabelText('Regular fan speed (%)')).toBeTruthy()
    expect(controls.getByLabelText('Maximum fan speed (%)')).toBeTruthy()
    expect(controls.getByLabelText(/^Regular Fan Speed at Layer/)).toBeTruthy()
    expect(controls.getByLabelText(/^Minimum Layer Time \(s\)/)).toBeTruthy()
    expect(controls.getByLabelText(/^Minimum Speed \(mm\/s\)/)).toBeTruthy()
    expect(within(rendered.container).queryByLabelText(/^Initial Fan Speed/)).toBeNull()
  })

  it('marks explicit filament customizations with the stronger ownership state', () => {
    const rendered = render(
      <MaterialSettingsEditor
        plates={[]}
        catalog={[]}
        settings={settings}
        baseSettings={{ ...settings, flow_percent: '100' }}
        overrideKeys={['flow_percent']}
      />,
    )

    const flowField = within(rendered.container)
      .getByLabelText('Flow (%)')
      .closest('.setting-field')
    expect(flowField?.className).toContain('setting-field--customized')
    expect(within(flowField as HTMLElement).getByText(/Customized · Template: 100/)).toBeTruthy()
  })
})
