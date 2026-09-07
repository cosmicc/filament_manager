import { describe, expect, it } from 'vitest'
import { costPerGram, currencyAmount, dateTime, grams, percent, preserveUnchangedNumber, titleCase } from './format'

describe('presentation formatting', () => {
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
