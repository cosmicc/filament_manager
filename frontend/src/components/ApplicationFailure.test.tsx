// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ApplicationFailure } from './ApplicationFailure'

describe('ApplicationFailure', () => {
  it('presents an accessible recovery action after a browser render failure', () => {
    render(<ApplicationFailure />)

    expect(screen.getByRole('alert')).toBeTruthy()
    expect(
      screen.getByRole('heading', { name: 'Filament Manager could not continue' }),
    ).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reload application' })).toBeTruthy()
  })
})
