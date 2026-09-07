import { useState } from 'react'
import { analyzeThumbnailContrast, DEFAULT_THUMBNAIL_CONTRAST, type ThumbnailContrast } from '../lib/thumbnailContrast'

// Cache only small presentation decisions, not images or pixels. History and
// dashboard mounts share the immutable authenticated URL; eviction bounds memory.
const contrastCache = new Map<string, ThumbnailContrast>()
const CACHE_LIMIT = 128
const SAMPLE_SIDE = 64

/** Accept only local captured-print images; never fetch a slicer/printer origin. */
function storedThumbnailPath(src: string): string | null {
  try {
    const url = new URL(src, window.location.origin)
    return url.origin === window.location.origin && !url.username && !url.password
      && !url.search && !url.hash && /^\/api\/v1\/prints\/[^/]+\/thumbnail$/.test(url.pathname)
      ? url.pathname : null
  } catch {
    return null
  }
}

/** Analyze the already-loaded bounded raster, with no additional HTTP request. */
function imageContrast(image: HTMLImageElement, src: string): ThumbnailContrast {
  const cached = contrastCache.get(src)
  if (cached) return cached
  if (!image.naturalWidth || !image.naturalHeight || image.naturalWidth > 512 || image.naturalHeight > 512) {
    return DEFAULT_THUMBNAIL_CONTRAST
  }
  try {
    const canvas = document.createElement('canvas')
    const scale = Math.min(1, SAMPLE_SIDE / Math.max(image.naturalWidth, image.naturalHeight))
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) return DEFAULT_THUMBNAIL_CONTRAST
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    const result = analyzeThumbnailContrast(context.getImageData(0, 0, canvas.width, canvas.height).data)
    if (contrastCache.size >= CACHE_LIMIT) contrastCache.delete(contrastCache.keys().next().value!)
    contrastCache.set(src, result)
    return result
  } catch {
    // Canvas may be disabled or unreadable. Preserve the image and neutral frame;
    // do not send image contents or URLs to telemetry, and never fail the page.
    return DEFAULT_THUMBNAIL_CONTRAST
  }
}

type Props = { src: string; alt: string; className: string }

/** Keep existing layout classes while sharing accessible adaptive presentation. */
export function PrintThumbnail(props: Props) {
  return <LoadedPrintThumbnail key={props.src} {...props} />
}

function LoadedPrintThumbnail({ src, alt, className }: Props) {
  const path = storedThumbnailPath(src)
  const [appearance, setAppearance] = useState(() => path ? contrastCache.get(path) ?? DEFAULT_THUMBNAIL_CONTRAST : DEFAULT_THUMBNAIL_CONTRAST)
  const [failed, setFailed] = useState(false)
  const filter = [
    `brightness(${appearance.brightness}) contrast(${appearance.contrast})`,
    // Opposite subtle silhouettes retain both light and dark parts of mixed models.
    appearance.outline ? 'drop-shadow(1px 0 0 var(--thumbnail-dark)) drop-shadow(-1px 0 0 var(--thumbnail-light))' : '',
  ].join(' ')
  return <span className={`${className} adaptive-thumbnail adaptive-thumbnail--${appearance.backdrop}`}
    data-thumbnail-contrast={appearance.brightness !== 1 || appearance.contrast !== 1 ? 'enhanced' : 'original'}
    title="Automatic preview contrast; the stored thumbnail is unchanged.">
    {path && !failed ? <img src={path} alt={alt} decoding="async" style={{ filter }}
      onLoad={(event) => setAppearance(imageContrast(event.currentTarget, path))}
      onError={() => setFailed(true)} />
      : <span className="adaptive-thumbnail__unavailable" role={alt ? 'img' : undefined} aria-label={alt ? `${alt}: thumbnail unavailable` : undefined} aria-hidden={alt ? undefined : true}>Preview unavailable</span>}
  </span>
}
