import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { type CSSProperties, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, CuraSettingCatalogItem, Filament, MaterialProfile, MaterialSettings, MaterialTemplate, Printer, ProfileStatistics } from '../api/types'
import { compactNumber } from '../lib/format'
import { getMaterialSettingDifferences, getScopeMismatchFields } from '../lib/materialComparison'
import { EditorSection } from './EditorSection'
import { Modal } from './Modal'

interface ComparisonTarget {
  key: string
  type: 'profile' | 'template'
  sourceId: string
  label: string
  optionLabel: string
  printerId: string
  nozzleDiameterMm: string
  settings: MaterialSettings
}

function filamentLabel(profile: MaterialProfile, filaments: Filament[]): string {
  const filament = filaments.find((item) => item.id === profile.filament_product_id)
  if (!filament) return 'Unknown filament profile'
  return `${[filament.vendor_name, filament.product_name ?? filament.material_type].filter(Boolean).join(' ')} · ${filament.color_name}`
}

function scopeLabel(target: { printerId: string; nozzleDiameterMm: string }, printers: Printer[]): string {
  return `${printers.find((item) => item.id === target.printerId)?.name ?? 'Unknown printer'} · ${target.nozzleDiameterMm} mm nozzle`
}

export function MaterialComparisonModal({ profiles, templates, printers, filaments, plates, catalog, initialProfileId, initialTargetKey, onClose }: {
  profiles: MaterialProfile[]
  templates: MaterialTemplate[]
  printers: Printer[]
  filaments: Filament[]
  plates: BuildPlate[]
  catalog: CuraSettingCatalogItem[]
  initialProfileId?: string
  initialTargetKey?: string
  onClose: () => void
}) {
  const targets = useMemo<ComparisonTarget[]>(() => [
    ...profiles.map((profile) => ({ key: `profile:${profile.id}`, type: 'profile' as const, sourceId: profile.id, label: filamentLabel(profile, filaments), optionLabel: `${filamentLabel(profile, filaments)} · ${scopeLabel({ printerId: profile.printer_id, nozzleDiameterMm: profile.nozzle_diameter_mm }, printers)}`, printerId: profile.printer_id, nozzleDiameterMm: profile.nozzle_diameter_mm, settings: profile })),
    ...templates.flatMap((template) => template.revisions.slice(0, 1).map((snapshot) => ({ key: `template:${snapshot.id}`, type: 'template' as const, sourceId: snapshot.id, label: template.name, optionLabel: `${template.name} · ${scopeLabel({ printerId: template.printer_id, nozzleDiameterMm: template.nozzle_diameter_mm }, printers)}`, printerId: template.printer_id, nozzleDiameterMm: template.nozzle_diameter_mm, settings: snapshot.settings }))),
  ], [filaments, printers, profiles, templates])
  const initialBaseline = `profile:${initialProfileId ?? profiles[0]?.id ?? ''}`
  const initialSecond = initialTargetKey && targets.some((item) => item.key === initialTargetKey)
    ? initialTargetKey
    : targets.find((item) => item.key !== initialBaseline)?.key
  const [selectedKeys, setSelectedKeys] = useState<string[]>([initialBaseline, initialSecond].filter((item): item is string => Boolean(item)))
  const selected = selectedKeys.map((key) => targets.find((target) => target.key === key)).filter((item): item is ComparisonTarget => Boolean(item))
  const baseline = selected[0]
  const compared = selected.slice(1)
  const pairDifferences = compared.map((target) => ({ target, differences: baseline ? getMaterialSettingDifferences(baseline.settings, target.settings, catalog, plates) : [] }))
  const differenceRows = useMemo(() => {
    const rows = new Map<string, { label: string; values: Map<string, string> }>()
    for (const pair of pairDifferences) {
      for (const difference of pair.differences) {
        const row = rows.get(difference.key) ?? { label: difference.label, values: new Map([[baseline?.key ?? '', difference.leftDisplay]]) }
        row.values.set(pair.target.key, difference.rightDisplay)
        rows.set(difference.key, row)
      }
    }
    return [...rows.entries()].map(([key, row]) => ({ key, ...row }))
  }, [baseline?.key, pairDifferences])
  const profileIds = selected.filter((item) => item.type === 'profile').map((item) => item.sourceId)
  const statistics = useQuery({
    queryKey: ['profile-statistics', profileIds],
    queryFn: () => apiFetch<Record<string, ProfileStatistics>>(`/prints/profile-statistics?${profileIds.map((id) => `profile_id=${id}`).join('&')}`),
    enabled: profileIds.length > 0,
  })
  const scopeWarnings = compared.flatMap((target) => {
    if (!baseline) return []
    const fields = getScopeMismatchFields({ printerId: baseline.printerId, nozzleDiameterMm: baseline.nozzleDiameterMm }, { printerId: target.printerId, nozzleDiameterMm: target.nozzleDiameterMm })
    return fields.length ? [`${target.label}: ${fields.join(' and ')} differ`] : []
  })

  function toggleTarget(key: string) {
    setSelectedKeys((current) => current.includes(key) ? current.length > 2 ? current.filter((item) => item !== key) : current : current.length < 4 ? [...current, key] : current)
  }

  return <Modal title="Compare material settings" description="Select two to four current profiles or templates. The first selection is the baseline and only semantic differences are shown." onClose={onClose} size="wide" footer={<button className="button" onClick={onClose}>Close comparison</button>}>
    <div className="comparison-layout">
      <EditorSection title="Comparison set" description="Choose up to four current material settings. Cross-printer and cross-nozzle comparisons remain available with a clear warning."><div className="comparison-target-grid">{targets.map((target) => <label className="check-row" key={target.key}><input type="checkbox" checked={selectedKeys.includes(target.key)} disabled={!selectedKeys.includes(target.key) && selectedKeys.length >= 4} onChange={() => toggleTarget(target.key)} /><span><strong>{target.label}</strong><small>{target.optionLabel}</small></span></label>)}</div><small className="field-help">{selected.length}/4 selected · first selected is the baseline</small></EditorSection>
      {scopeWarnings.length ? <div className="comparison-scope-warning" role="alert"><AlertTriangle size={19} /><span><strong>Scope warning</strong>{scopeWarnings.map((warning) => <small key={warning}>{warning}</small>)}</span></div> : <div className="comparison-scope-match"><CheckCircle2 size={18} /> All selected printer and nozzle scopes match.</div>}
      <section className="comparison-results"><header><div><p className="eyebrow">Difference-only view</p><h3>{differenceRows.length} setting {differenceRows.length === 1 ? 'difference' : 'differences'}</h3></div></header>{differenceRows.length ? <div className="comparison-table comparison-table--multi" style={{ '--comparison-columns': selected.length } as CSSProperties}><div className="comparison-row comparison-row--multi comparison-row--header"><span>Setting</span>{selected.map((target) => <span key={target.key}>{target.label}</span>)}</div>{differenceRows.map((row) => <div className="comparison-row comparison-row--multi" key={row.key}><div className="comparison-setting"><strong>{row.label}</strong><small>{row.key}</small></div>{selected.map((target) => <div className="comparison-value" key={target.key}><span>{target.label}</span><strong>{row.values.get(target.key) ?? 'Same as baseline'}</strong></div>)}</div>)}</div> : <div className="comparison-empty"><CheckCircle2 size={22} /><div><strong>No setting differences</strong><p>The selected materials store equivalent settings.</p></div></div>}</section>
      <section className="comparison-results"><header><div><p className="eyebrow">Recorded outcomes</p><h3>Success rate by profile</h3></div></header><div className="comparison-stat-grid">{selected.map((target) => { const stats = target.type === 'profile' ? statistics.data?.[target.sourceId] : undefined; return <article key={target.key}><strong>{target.label}</strong>{target.type === 'template' ? <span>N/A</span> : <span>{stats?.success_rate_percent ? `${compactNumber(stats.success_rate_percent, 1)}%` : 'No ratings'}</span>}<small>{target.type === 'template' ? 'Templates are not printed directly.' : stats?.low_sample ? `Low sample · ${stats.rated_prints} rated` : `${stats?.rated_prints ?? 0} rated prints`}</small></article> })}</div></section>
    </div>
  </Modal>
}
