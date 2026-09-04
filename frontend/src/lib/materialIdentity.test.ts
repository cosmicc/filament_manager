import { describe, expect, it } from 'vitest'
import { materialIdentitySummary, materialModifierSummary } from './materialIdentity'

describe('material identity', () => {
  it('omits absent filler values and a standard finish', () => {
    const material = {
      material_type: 'PLA',
      color_name: 'Green',
      filler: 'None',
      finish: 'Standard',
    }

    expect(materialIdentitySummary(material)).toBe('PLA · Green')
    expect(materialModifierSummary(material)).toBeNull()
    expect(materialModifierSummary({ filler: ' sTaNdArD ', finish: 'Silk' })).toBe('Silk')
  })

  it('omits blank and explicit none values', () => {
    const material = {
      material_type: 'PLA',
      color_name: 'Green',
      filler: ' ',
      finish: 'None',
    }

    expect(materialIdentitySummary(material)).toBe('PLA · Green')
    expect(materialModifierSummary(material)).toBeNull()
  })

  it('omits explicit not-specified placeholders', () => {
    const material = {
      material_type: 'PLA',
      color_name: 'Green',
      filler: 'Not specified',
      finish: 'not specified',
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
