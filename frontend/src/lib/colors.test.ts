import { describe, expect, it } from 'vitest'
import { filamentSwatchStyle } from './colors'

describe('filament swatches', () => {
  it('renders two or three custom colors as a segmented gradient', () => {
    const style = filamentSwatchStyle('multicolor', ['FF0000', '00FF00', '0000FF']) as Record<string, string>

    expect(style['--swatch']).toBe('#FF0000')
    expect(style['--swatch-background']).toContain('conic-gradient')
    expect(style['--swatch-background']).toContain('#0000FF')
  })

  it('renders rainbow independently of a supplied palette', () => {
    const style = filamentSwatchStyle('rainbow', []) as Record<string, string>

    expect(style['--swatch-background']).toContain('#E53935')
    expect(style['--swatch-background']).toContain('#8E24AA')
  })
})
