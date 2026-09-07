import type { Page } from '@playwright/test'

export type ThumbnailFixture = 'black' | 'white' | 'blue' | 'yellow' | 'mixed' | 'opaque'

/** Generate raster test evidence, including real alpha, without external assets. */
export async function thumbnailFixture(page: Page, kind: ThumbnailFixture): Promise<Buffer> {
  const encoded = await page.evaluate((variant) => {
    const canvas = document.createElement('canvas')
    canvas.width = 128
    canvas.height = 96
    const context = canvas.getContext('2d')!
    if (variant === 'opaque') {
      context.fillStyle = '#282828'
      context.fillRect(0, 0, 128, 96)
    }
    const colors = { black: '#080808', white: '#f8f8f8', blue: '#123c82', yellow: '#f0ec20', mixed: '#080808', opaque: '#080808' }
    context.fillStyle = colors[variant]
    context.beginPath()
    context.moveTo(64, 12)
    context.lineTo(105, 34)
    context.lineTo(105, 68)
    context.lineTo(64, 88)
    context.lineTo(23, 68)
    context.lineTo(23, 34)
    context.closePath()
    context.fill()
    if (variant === 'mixed') {
      context.fillStyle = '#f8f8f8'
      context.beginPath()
      context.moveTo(64, 12)
      context.lineTo(105, 34)
      context.lineTo(105, 68)
      context.lineTo(64, 88)
      context.closePath()
      context.fill()
    }
    context.strokeStyle = variant === 'white' || variant === 'yellow' ? '#a0a0a0' : '#343434'
    context.lineWidth = 2
    context.beginPath()
    context.moveTo(23, 34)
    context.lineTo(64, 55)
    context.lineTo(105, 34)
    context.moveTo(64, 55)
    context.lineTo(64, 88)
    context.stroke()
    return canvas.toDataURL('image/png').split(',')[1]
  }, kind)
  return Buffer.from(encoded, 'base64')
}
