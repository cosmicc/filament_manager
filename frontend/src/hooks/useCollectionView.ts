import { useEffect, useState } from 'react'

export type CollectionView = 'list' | 'cards' | 'detailed'

const COLLECTION_VIEW_STORAGE_PREFIX = 'filament-manager.collection-view.'
const collectionViews: CollectionView[] = ['list', 'cards', 'detailed']

function storedCollectionView(storageKey: string, defaultView: CollectionView): CollectionView {
  try {
    const stored = window.localStorage.getItem(`${COLLECTION_VIEW_STORAGE_PREFIX}${storageKey}`)
    return collectionViews.includes(stored as CollectionView) ? (stored as CollectionView) : defaultView
  } catch {
    return defaultView
  }
}

/** Remembers one catalog presentation independently for each inventory page. */
export function useCollectionView(storageKey: string, defaultView: CollectionView) {
  const [view, setView] = useState<CollectionView>(() => storedCollectionView(storageKey, defaultView))

  useEffect(() => {
    try {
      window.localStorage.setItem(`${COLLECTION_VIEW_STORAGE_PREFIX}${storageKey}`, view)
    } catch {
      // A denied storage API should not prevent the inventory catalog from working.
    }
  }, [storageKey, view])

  return [view, setView] as const
}
