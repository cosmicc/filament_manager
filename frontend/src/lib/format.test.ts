import { describe, expect, it } from 'vitest'
import { dateTime, grams, percent, titleCase } from './format'

describe('presentation formatting', () => {
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
})
