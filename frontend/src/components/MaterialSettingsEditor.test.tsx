// @vitest-environment jsdom

import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { MaterialSettings } from '../api/types'
import { MaterialSettingsEditor, settingsFromForm } from './MaterialSettingsEditor'

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
  ironing_flow_percent: null,
  ironing_speed_mm_s: null,
  ironing_line_spacing_mm: null,
  filament_density_g_cm3: '1.24',
  preferred_build_plate_surface_id: null,
  cura_extensions: {},
}

describe('MaterialSettingsEditor validation', () => {
  it('shows only the three requested temperature controls', () => {
    const rendered = render(<MaterialSettingsEditor settings={settings} catalog={[]} plates={[]} />)

    expect(screen.getByLabelText('Printing temperature (°C)')).toBeTruthy()
    expect(screen.getByLabelText('Build volume temperature (°C)')).toBeTruthy()
    expect(screen.getByLabelText('Build plate temperature (°C)')).toBeTruthy()
    expect(screen.queryByText(/Default .*temperature/i)).toBeNull()
    expect(screen.queryByLabelText('Chamber temperature (°C)')).toBeNull()
    rendered.unmount()
  })

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

  it('serializes all editable ironing values from a template form', () => {
    const rendered = render(
      <form data-testid="settings-form">
        <MaterialSettingsEditor settings={settings} catalog={[]} plates={[]} scope="template" />
      </form>,
    )
    const controls = within(rendered.container)
    fireEvent.change(controls.getByLabelText('Ironing flow (%)'), { target: { value: '12' } })
    fireEvent.change(controls.getByLabelText('Ironing speed (mm/s)'), { target: { value: '25' } })
    fireEvent.change(controls.getByLabelText('Ironing line spacing (mm)'), { target: { value: '0.12' } })

    const serialized = settingsFromForm(
      rendered.getByTestId('settings-form') as HTMLFormElement,
      [],
      'template',
    )
    expect(serialized.ironing_flow_percent).toBe('12')
    expect(serialized.ironing_speed_mm_s).toBe('25')
    expect(serialized.ironing_line_spacing_mm).toBe('0.12')
  })

  it('groups every requested Cura cooling control and allows initial fan speed editing', () => {
    const rendered = render(
      <MaterialSettingsEditor
        plates={[]}
        catalog={[
          { key: 'cool_fan_full_layer', label: 'Regular Fan Speed at Layer', value_type: 'number', unit: null, editable: true, template_only: false },
          { key: 'cool_min_layer_time', label: 'Minimum Layer Time', value_type: 'number', unit: 's', editable: true, template_only: false },
          { key: 'cool_min_speed', label: 'Minimum Speed', value_type: 'number', unit: 'mm/s', editable: true, template_only: false },
          { key: 'cool_fan_speed_0', label: 'Initial Fan Speed', value_type: 'number', unit: '%', editable: true, template_only: false },
        ]}
      />,
    )

    const cooling = within(rendered.container).getByRole('heading', { name: 'Cooling' }).closest('section')
    expect(cooling).not.toBeNull()
    const controls = within(cooling as HTMLElement)
    expect(controls.getByLabelText(/^Regular fan speed \(%\)/)).toBeTruthy()
    expect(controls.getByLabelText(/^Maximum fan speed \(%\)/)).toBeTruthy()
    expect(controls.getByLabelText(/^Regular Fan Speed at Layer/)).toBeTruthy()
    expect(controls.getByLabelText(/^Minimum Layer Time \(s\)/)).toBeTruthy()
    expect(controls.getByLabelText(/^Minimum Speed \(mm\/s\)/)).toBeTruthy()
    expect(controls.getByLabelText(/^Initial Fan Speed/)).toBeTruthy()
  })

  it('shows every cooling control in filament profiles with the correct minimums', () => {
    const rendered = render(
      <MaterialSettingsEditor
        settings={settings}
        baseSettings={settings}
        plates={[]}
        scope="profile"
        catalog={[
          { key: 'cool_fan_full_layer', label: 'Regular Fan Speed at Layer', value_type: 'number', unit: null, editable: true, template_only: false },
          { key: 'cool_min_layer_time', label: 'Minimum Layer Time', value_type: 'number', unit: 's', editable: true, template_only: false },
          { key: 'cool_min_layer_time_fan_speed_max', label: 'Minimum Layer Time at Maximum Fan', value_type: 'number', unit: 's', editable: true, template_only: false },
          { key: 'cool_min_speed', label: 'Minimum Speed', value_type: 'number', unit: 'mm/s', editable: true, template_only: false },
          { key: 'cool_fan_speed_0', label: 'Initial Fan Speed', value_type: 'number', unit: '%', editable: true, template_only: false },
        ]}
      />,
    )
    const controls = within(rendered.container)

    expect(controls.getByLabelText(/^Enable print cooling/)).toBeTruthy()
    expect(controls.getByLabelText(/^Regular fan speed/).getAttribute('min')).toBe('0')
    expect(controls.getByLabelText(/^Maximum fan speed/).getAttribute('min')).toBe('0')
    expect(controls.getByLabelText(/^Regular Fan Speed at Layer/).getAttribute('min')).toBe('1')
    expect(controls.getByLabelText(/^Minimum Layer Time \(s\)/)).toBeTruthy()
    expect(controls.getByLabelText(/^Minimum Layer Time at Maximum Fan/)).toBeTruthy()
    expect(controls.getByLabelText(/^Minimum Speed/)).toBeTruthy()
    expect(controls.getByLabelText(/^Initial Fan Speed/)).toBeTruthy()
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

  it('shows template-only acceleration and Klipper controls only in template editors', () => {
    const catalog = [
      { key: 'acceleration_enabled', label: 'Enable Acceleration Control', value_type: 'boolean' as const, unit: null, editable: false, template_only: true },
      { key: 'acceleration_print', label: 'Print Acceleration', value_type: 'number' as const, unit: 'mm/s²', editable: true, template_only: true },
      { key: 'acceleration_travel', label: 'Travel Acceleration', value_type: 'number' as const, unit: 'mm/s²', editable: true, template_only: true },
      { key: 'klipper_smooth_time_enable', label: 'Enable Klipper Smooth Time', value_type: 'boolean' as const, unit: null, editable: true, template_only: true },
    ]
    const template = render(
      <MaterialSettingsEditor settings={settings} plates={[]} catalog={catalog} scope="template" />,
    )
    const templateControls = within(template.container)

    expect(templateControls.getByLabelText(/^Print Acceleration/)).toBeTruthy()
    expect(templateControls.getByLabelText(/^Travel Acceleration/)).toBeTruthy()
    expect(templateControls.getByLabelText(/^Klipper pressure advance/)).toBeTruthy()
    expect(templateControls.getAllByText('Template only').length).toBeGreaterThanOrEqual(3)
    expect(templateControls.queryByLabelText('Enable Acceleration Control')).toBeNull()
    template.unmount()

    const profile = render(
      <MaterialSettingsEditor
        settings={settings}
        baseSettings={settings}
        plates={[]}
        catalog={catalog}
        scope="profile"
      />,
    )
    const profileControls = within(profile.container)
    expect(profileControls.queryByLabelText(/^Print Acceleration/)).toBeNull()
    expect(profileControls.queryByLabelText(/^Travel Acceleration/)).toBeNull()
    expect(profileControls.getByLabelText(/^Klipper pressure advance/)).toBeTruthy()
    expect(profileControls.queryByLabelText('Enable Klipper Smooth Time')).toBeNull()
  })

  it('copies a blank setting from any active template source and then hides the chooser', () => {
    const rendered = render(
      <MaterialSettingsEditor
        settings={settings}
        plates={[]}
        catalog={[]}
        copySources={[{
          id: 'template-petg',
          label: 'Template PETG · Workshop printer · 0.4 mm',
          settings: { ...settings, chamber_temp_c: '45' },
        }]}
        scope="template"
      />,
    )

    expect(screen.queryByLabelText('Enable ironing')).toBeNull()
    const chooser = within(rendered.container).getByLabelText('Copy Build volume temperature from another template')
    fireEvent.change(chooser, { target: { value: 'template-petg' } })
    expect((within(rendered.container).getByLabelText('Build volume temperature (°C)') as HTMLInputElement).value).toBe('45')
    expect(within(rendered.container).queryByLabelText('Copy Build volume temperature from another template')).toBeNull()
  })

  it('explains when a blank value has no populated active template source', () => {
    const rendered = render(
      <MaterialSettingsEditor settings={settings} plates={[]} catalog={[]} scope="template" />,
    )

    const chooser = within(rendered.container).getByLabelText('Copy Build volume temperature from another template')
    expect((chooser as HTMLSelectElement).disabled).toBe(true)
    expect(within(chooser).getByText('No other active template has a value')).toBeTruthy()
  })
})
