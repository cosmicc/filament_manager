import { describe, expect, it } from 'vitest'
import { analyzeThumbnailContrast, DEFAULT_THUMBNAIL_CONTRAST } from './thumbnailContrast'

const pixels = (...colors: number[][]) => new Uint8ClampedArray(colors.flat())

describe('thumbnail contrast', () => {
  it('puts black and dark colored models on light gray without recoloring them', () => {
    for (const color of [[0, 0, 0, 255], [40, 20, 80, 255], [220, 20, 10, 255]]) {
      expect(analyzeThumbnailContrast(pixels(color, [255, 255, 255, 0]))).toEqual({
        backdrop: 'light', outline: false, brightness: 1, contrast: 1,
      })
    }
  })
  it('puts white and bright colored models on dark gray', () => {
    for (const color of [[255, 255, 255, 255], [240, 240, 20, 255]]) {
      expect(analyzeThumbnailContrast(pixels(color, [0, 0, 0, 0])).backdrop).toBe('dark')
    }
  })
  it('ignores transparent RGB and almost invisible antialiasing', () => {
    expect(analyzeThumbnailContrast(pixels(
      [0, 0, 0, 255], ...Array.from({ length: 100 }, () => [255, 255, 255, 10]),
    )).backdrop).toBe('light')
  })
  it('uses a neutral background and outline for mixed transparent models', () => {
    expect(analyzeThumbnailContrast(pixels(
      [0, 0, 0, 255], [255, 255, 255, 255], [0, 0, 0, 0],
    ))).toEqual({ backdrop: 'neutral', outline: true, brightness: 1, contrast: 1 })
  })
  it('boosts a dark opaque thumbnail without modifying the source pixels', () => {
    const source = pixels([0, 0, 0, 255], [45, 45, 45, 255])
    const before = source.slice()
    const result = analyzeThumbnailContrast(source)
    expect(result.brightness).toBe(4)
    expect(result.contrast).toBe(1)
    expect(source).toEqual(before)
  })
  it('does not boost a well-exposed opaque image or invent detail in a flat image', () => {
    for (const source of [
      pixels([0, 0, 0, 255], [255, 255, 255, 255]),
      pixels([0, 0, 0, 255], [0, 0, 0, 255]),
    ]) {
      const result = analyzeThumbnailContrast(source)
      expect(result.brightness).toBe(1)
      expect(result.contrast).toBe(1)
    }
  })
  it('bounds processing and tolerates empty or invalid samples', () => {
    for (const source of [new Uint8ClampedArray(), pixels([1, 2, 3]), new Uint8ClampedArray(64 * 64 * 4 + 4), pixels([0, 0, 0, 0])]) {
      expect(analyzeThumbnailContrast(source)).toEqual(DEFAULT_THUMBNAIL_CONTRAST)
    }
  })
})
