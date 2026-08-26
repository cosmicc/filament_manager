import { describe, expect, it } from 'vitest'
import { materialIdentitySummary, materialModifierSummary } from './materialIdentity'

describe('material identity', () => {
  it('omits implied filler and finish values from filament and spool titles', () => {
    const material = {
      material_type: 'PLA',
      color_name: 'Green',
      filler: 'None',
      finish: 'Standard',
    }

    expect(materialIdentitySummary(material)).toBe('PLA · Green')
    expect(materialModifierSummary(material)).toBeNull()
  })

  it('retains meaningful filler and finish modifiers', () => {
    const material = {
      material_type: 'PLA',
      color_name: 'Green',
      filler: 'Carbon Fiber',
      finish: 'Silk',
    }

    expect(materialIdentitySummary(material)).toBe('PLA · Green · Carbon Fiber · Silk')
    expect(materialModifierSummary(material)).toBe('Carbon Fiber · Silk')
  })
})
