/** Bounded, display-only thumbnail analysis. Never changes captured print data. */
export type ThumbnailBackdrop = 'light' | 'dark' | 'neutral'

export interface ThumbnailContrast {
  backdrop: ThumbnailBackdrop
  outline: boolean
  brightness: number
  contrast: number
}

export const DEFAULT_THUMBNAIL_CONTRAST: ThumbnailContrast = {
  backdrop: 'neutral', outline: false, brightness: 1, contrast: 1,
}

/** Inspect at most a 64 x 64 RGBA sample, ignoring invisible RGB and edge halos. */
export function analyzeThumbnailContrast(pixels: Uint8ClampedArray): ThumbnailContrast {
  if (!pixels.length || pixels.length % 4 !== 0 || pixels.length > 64 * 64 * 4) {
    return DEFAULT_THUMBNAIL_CONTRAST
  }
  const histogram = new Float64Array(256)
  let total = 0
  let dark = 0
  let light = 0
  let transparent = 0
  for (let offset = 0; offset < pixels.length; offset += 4) {
    const alpha = pixels[offset + 3] / 255
    if (alpha < 0.95) transparent++
    if (alpha < 0.1) continue
    // Perceived brightness, weighted by visible coverage rather than empty canvas.
    const brightness = Math.round(0.2126 * pixels[offset] + 0.7152 * pixels[offset + 1] + 0.0722 * pixels[offset + 2])
    histogram[brightness] += alpha
    total += alpha
    if (brightness < 100) dark += alpha
    if (brightness > 180) light += alpha
  }
  if (!total) return DEFAULT_THUMBNAIL_CONTRAST
  const percentile = (fraction: number) => {
    let sum = 0
    for (let index = 0; index < histogram.length; index++) {
      sum += histogram[index]
      if (sum >= total * fraction) return index / 255
    }
    return 1
  }
  const mixed = dark / total >= 0.2 && light / total >= 0.2
  const result: ThumbnailContrast = {
    backdrop: mixed ? 'neutral' : percentile(0.5) < 0.55 ? 'light' : 'dark',
    outline: mixed && transparent > 0,
    brightness: 1, contrast: 1,
  }
  // A background cannot help opaque pixels. Expand an existing dark tonal range
  // conservatively, without inversion, segmentation, or inventing missing detail.
  const low = percentile(0.01)
  const high = percentile(0.99)
  const range = high - low
  if (transparent === 0 && high < 0.5 && range >= 0.025 && range < 0.4) {
    const gain = Math.min(4, 0.75 / range)
    result.contrast = Math.min(3, 1 + 2 * low * gain)
    result.brightness = gain / result.contrast
  }
  return result
}
