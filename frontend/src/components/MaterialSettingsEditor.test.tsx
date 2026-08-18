// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
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
})
