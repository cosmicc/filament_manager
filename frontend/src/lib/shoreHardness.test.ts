import { describe, expect, it } from 'vitest'
import type { MaterialProfile } from '../api/types'
import { formatHardness, hardnessByFilament, hardnessRank, oppositeHardness } from './shoreHardness'

describe('Shore hardness reference', () => {
  it('shows estimates only in the verified overlap and retains the declared scale', () => {
    expect(formatHardness({ scale: 'A', value: '95' })).toBe('95A (≈46D)')
    expect(formatHardness({ scale: 'D', value: '39' })).toBe('39D (≈90A)')
    expect(oppositeHardness({ scale: 'A', value: '80' })).toBe(29)
    for (const [scale, value] of [['A', '0'], ['A', '29'], ['D', '5'], ['D', '59'], ['D', '100']] as const) {
      expect(formatHardness({ scale, value })).toBe(`${value}${scale}`)
    }
    expect(formatHardness({ scale: 'A', value: '98' })).toBe('98A (≈53D)')
    expect(formatHardness({ scale: 'D', value: '58' })).toBe('58D (≈100A)')
    expect(formatHardness(null)).toBe('Not set')
  })
  it('orders mixed scales and preserves distinct and unknown scope values', () => {
    expect(hardnessRank({ scale: 'A', value: '95' })).toBe(hardnessRank({ scale: 'D', value: '46' }))
    expect(hardnessRank({ scale: 'D', value: '75' })).toBeGreaterThan(hardnessRank({ scale: 'A', value: '95' }))
    const profiles = [{ filament_product_id: 'one', shore_hardness: { scale: 'A', value: '95' } }, { filament_product_id: 'one', shore_hardness: null }, { filament_product_id: 'one', shore_hardness: { scale: 'D', value: '75' } }] as MaterialProfile[]
    expect(hardnessByFilament(profiles).get('one')).toEqual({ label: '95A (≈46D) / Not set / 75D', rank: 46 })
  })
})
