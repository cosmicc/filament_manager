// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { StatusPill } from './StatusPill'

afterEach(cleanup)
it.each(['warning', 'warn', 'degraded', 'pending'])('uses theme warning colors for %s', status => {
  render(<StatusPill status={status} />)
  expect(screen.getByText(status).classList.contains('status-pill--warning')).toBe(true)
})
