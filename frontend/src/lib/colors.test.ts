import { describe, expect, it } from 'vitest'
import { filamentSwatchStyle } from './colors'

describe('filament swatches', () => {
  it('renders two or three custom colors as a segmented gradient', () => {
    const twoColorStyle = filamentSwatchStyle('multicolor', ['FF0000', '00FF00']) as Record<string, string>
    const threeColorStyle = filamentSwatchStyle('multicolor', ['FF0000', '00FF00', '0000FF', 'FFFFFF']) as Record<string, string>

    expect(twoColorStyle['--swatch']).toBe('#FF0000')
    expect(twoColorStyle['--spool-fill']).toContain('#FF0000 0%')
    expect(twoColorStyle['--spool-fill']).toContain('#00FF00 100%')
    expect(threeColorStyle['--spool-fill']).toContain('conic-gradient')
    expect(threeColorStyle['--spool-fill']).toContain('#0000FF')
    expect(threeColorStyle['--spool-fill']).not.toContain('#FFFFFF')
  })

  it('renders rainbow as a continuous spectrum independently of a supplied palette', () => {
    const style = filamentSwatchStyle('rainbow', []) as Record<string, string>

    expect(style['--spool-fill']).toContain('#E53935')
    expect(style['--spool-fill']).toContain('#8E24AA')
    expect(style['--spool-fill']).not.toContain('%')
  })
})
