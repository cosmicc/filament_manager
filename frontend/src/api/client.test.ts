import { describe, expect, it } from 'vitest'
import { actionableApiError, ApiClientError, validationMessagesFor } from './client'

describe('validationMessagesFor', () => {
  it('maps nested API validation details into editor-relative fields', () => {
    const error = new ApiClientError(422, 'validation_error', 'Request validation failed', [
      { field: 'settings.flow_percent', message: 'Input should be greater than 0', type: 'greater_than' },
      {
        field: 'settings.cura_extensions.klipper_smooth_time_factor',
        message: 'Klipper smooth time must be between 0.001 and 0.2',
        type: 'value_error',
      },
    ])

    expect(validationMessagesFor(error, 'settings')).toEqual({
      flow_percent: ['Input should be greater than 0'],
      'cura_extensions.klipper_smooth_time_factor': [
        'Klipper smooth time must be between 0.001 and 0.2',
      ],
    })
  })

  it('includes a safe diagnostic reference for unexpected server failures', () => {
    const error = new ApiClientError(
      500,
      'internal_error',
      'The request could not be completed',
      [],
      'safe-correlation-reference',
    )

    expect(actionableApiError(error)).toContain('internal_error · HTTP 500')
    expect(actionableApiError(error)).toContain('reference safe-correlation-reference')
    expect(actionableApiError(error)).toContain('Diagnostics')
  })
})
