// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PrintThumbnail } from './PrintThumbnail'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
const path = (id: string) => `/api/v1/prints/${id}/thumbnail`

function loadImage() {
  const image = screen.getByAltText('Preview') as HTMLImageElement
  Object.defineProperties(image, { naturalWidth: { value: 128 }, naturalHeight: { value: 128 } })
  fireEvent.load(image)
  return image
}

describe('PrintThumbnail', () => {
  it('samples the loaded image once and reuses the decision for later mounts', () => {
    const getImageData = vi.fn(() => ({ data: new Uint8ClampedArray([0, 0, 0, 255, 0, 0, 0, 0]) }))
    const drawImage = vi.fn()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage, getImageData } as unknown as CanvasRenderingContext2D)
    const props = { src: path('cached'), alt: 'Preview', className: 'print-thumbnail' }
    const first = render(<PrintThumbnail {...props} />)
    const image = loadImage()
    expect(image.parentElement?.className).toContain('adaptive-thumbnail--light')
    expect(drawImage.mock.calls[0].slice(1)).toEqual([0, 0, 64, 64])
    first.rerender(<PrintThumbnail {...props} />)
    expect(getImageData).toHaveBeenCalledTimes(1)
    first.unmount()
    render(<PrintThumbnail {...props} />)
    loadImage()
    expect(getImageData).toHaveBeenCalledTimes(1)
  })
  it('keeps the original image readable when canvas inspection is unavailable', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => { throw new Error('blocked') })
    render(<PrintThumbnail src={path('unreadable')} alt="Preview" className="print-thumbnail" />)
    const image = loadImage()
    expect(image.getAttribute('src')).toBe(path('unreadable'))
    expect(image.parentElement?.className).toContain('adaptive-thumbnail--neutral')
  })
  it('shows a safe fallback on image failure and resets when the source changes', () => {
    const view = render(<PrintThumbnail src={path('missing')} alt="Preview" className="print-thumbnail" />)
    fireEvent.error(screen.getByAltText('Preview'))
    expect(screen.getByRole('img', { name: 'Preview: thumbnail unavailable' })).toBeTruthy()
    view.rerender(<PrintThumbnail src={path('replacement')} alt="Preview" className="print-thumbnail" />)
    expect(screen.getByAltText('Preview').getAttribute('src')).toBe(path('replacement'))
  })
  it('never loads private origins, data URLs, or unrelated paths', () => {
    for (const src of ['https://printer.invalid/image.png', 'data:image/png;base64,AA==', '/other/image.png', path('id') + '?token=secret']) {
      const view = render(<PrintThumbnail src={src} alt="" className="print-thumbnail" />)
      expect(view.container.querySelector('img')).toBeNull()
      view.unmount()
    }
  })
})
