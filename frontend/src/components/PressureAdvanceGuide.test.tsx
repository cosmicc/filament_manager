// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { PressureAdvanceGuide } from './PressureAdvanceGuide'
import { pressureAdvanceFromHeight } from '../lib/pressureAdvanceCalculator'

afterEach(cleanup)
describe('Pressure Advance tower calculator', () => {
  it('calculates exact fixed-recipe values including zero and fractional heights', () => {
    expect(pressureAdvanceFromHeight('0')).toBe('0')
    expect(pressureAdvanceFromHeight('10')).toBe('0.2')
    expect(pressureAdvanceFromHeight('12.25')).toBe('0.245')
    expect(pressureAdvanceFromHeight('0.01')).toBe('0.0002')
    for (const invalid of ['', '-1', '101', 'NaN', '1e2', '1.234']) expect(pressureAdvanceFromHeight(invalid)).toBeNull()
  })
  it('shows preparation guidance and returns PA without saving', () => {
    render(<PressureAdvanceGuide />)
    expect(screen.getByText(/Run the Klipper Prep PA macro/)).toBeTruthy()
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '12.25' } })
    expect(screen.getByText('PA = 0.245')).toBeTruthy()
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '101' } })
    expect(screen.getByRole('spinbutton').getAttribute('aria-invalid')).toBe('true')
  })
})
