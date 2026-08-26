// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ login: vi.fn() }),
}))
vi.mock('../lib/version', () => ({ APP_VERSION: '0.5.6' }))

describe('LoginPage', () => {
  afterEach(cleanup)

  it('shows the running application version before authentication', () => {
    render(<LoginPage />)

    expect(screen.getByText('Filament Manager v0.5.6')).toBeTruthy()
  })
})
