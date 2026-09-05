import type { MaterialTemplate } from '../api/types'

/** Share the template-derived type vocabulary across both physical catalogs. */
export function MaterialTypeFilter({ templates, value, onChange }: {
  templates: MaterialTemplate[]
  value: string
  onChange: (value: string) => void
}) {
  const types = new Map<string, string>()
  for (const template of templates) {
    const label = template.material_type.trim()
    if (label) types.set(label.toLowerCase(), label)
  }
  return <label className="select-field">
    <span>Material</span>
    <select aria-label="Filter by filament type" value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">All</option>
      {[...types].sort((a, b) => a[1].localeCompare(b[1])).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select>
  </label>
}
