// @vitest-environment jsdom

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MaterialSettingsEditor } from './MaterialSettingsEditor'

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
})
