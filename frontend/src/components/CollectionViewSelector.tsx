import { LayoutGrid } from 'lucide-react'
import type { CollectionView } from '../hooks/useCollectionView'

export function CollectionViewSelector({
  label,
  value,
  onChange,
}: {
  label: string
  value: CollectionView
  onChange: (view: CollectionView) => void
}) {
  return (
    <label className="select-field collection-view-selector">
      <LayoutGrid size={17} />
      <span>View</span>
      <select
        aria-label={`${label} view`}
        value={value}
        onChange={(event) => onChange(event.target.value as CollectionView)}
      >
        <option value="list">List</option>
        <option value="cards">Cards</option>
        <option value="detailed">Detailed</option>
      </select>
    </label>
  )
}
