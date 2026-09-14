import { describe, expect, it } from 'vitest'
import { elapsedTime, compactNumber, inputNumber, costPerGram, currencyAmount, dateTime, grams, percent, preserveUnchangedNumber, titleCase } from './format'

describe('presentation formatting', () => {
  it('uses two elapsed units and never rounds a date into the future', () => {
    const now = Date.parse('2026-09-14T12:00:00Z')
    expect(elapsedTime('2026-09-11T08:00:00Z', now)).toBe('3 Days, 4 Hours ago')
    expect(elapsedTime('2026-09-05T12:00:00Z', now)).toBe('1 Week, 2 Days ago')
    expect(elapsedTime('2026-09-14T03:40:00Z', now)).toBe('8 Hours, 20 Minutes ago')
    expect(elapsedTime('2026-09-15T03:40:00Z', now)).toBe('Less than a minute ago')
  })
  it('caps presentation at two decimals without changing canonical precision', () => {
    expect(compactNumber('1.234567', 5)).toBe('1.23')
    expect(inputNumber('1.234567', 5)).toBe('1.23')
    expect(grams('1.234567', 5)).toBe('1.23 g')
    expect(preserveUnchangedNumber('1.23', '1.234567', 5)).toBe('1.234567')
  })
  it('retains precise filament diameter unless its displayed value changes', () => {
    expect(preserveUnchangedNumber('1.75', '1.75400', 2)).toBe('1.75400')
    expect(preserveUnchangedNumber('2.85', '1.75400', 2)).toBe('2.85')
  })
  it('formats mass and percentage values without changing source data', () => {
    expect(grams('812.400')).toBe('812 g')
    expect(grams('812.400', 1)).toBe('812.4 g')
    expect(percent('40.49')).toBe('40%')
  })

  it('presents controlled identifiers as labels', () => {
    expect(titleCase('needs_weighing')).toBe('Needs Weighing')
  })

  it('uses an explicit empty timestamp label', () => {
    expect(dateTime(null)).toBe('Never')
  })

  it('shows precise USD material cost in cents per gram', () => {
    expect(currencyAmount('15', 'USD')).toBe('$15.00')
    expect(costPerGram('0.015', 'USD')).toBe('1.5¢/g')
    expect(costPerGram(null, 'USD')).toBe('—')
  })
})
