import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import type {
  BuildPlate,
  CuraSettingCatalogItem,
  Filament,
  MaterialProfile,
  MaterialSettings,
  MaterialTemplate,
  Printer,
} from '../api/types'
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
  if (!filament) return `Unknown filament · profile v${profile.version}`
  const product = filament.product_name ?? filament.material_type
  return `${[filament.vendor_name, product].filter(Boolean).join(' ')} · ${filament.color_name} · profile v${profile.version}`
}

function scopeLabel(printerId: string, nozzleDiameterMm: string, printers: Printer[]): string {
  const printer = printers.find((item) => item.id === printerId)
  return `${printer?.name ?? 'Unknown printer'} · ${nozzleDiameterMm} mm nozzle`
}

function profileOptionLabel(profile: MaterialProfile, filaments: Filament[], printers: Printer[]): string {
  return `${filamentLabel(profile, filaments)} · ${profile.status.replaceAll('_', ' ')} · ${scopeLabel(profile.printer_id, profile.nozzle_diameter_mm, printers)}`
}

export function MaterialComparisonModal({
  profiles,
  templates,
  printers,
  filaments,
  plates,
  catalog,
  initialProfileId,
  initialTargetKey,
  onClose,
}: {
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
  const [profileId, setProfileId] = useState(initialProfileId ?? profiles[0]?.id ?? '')
  const [targetKey, setTargetKey] = useState(initialTargetKey ?? '')
  const targets = useMemo<ComparisonTarget[]>(() => [
    ...profiles.map((profile) => ({
      key: `profile:${profile.id}`,
      type: 'profile' as const,
      sourceId: profile.id,
      label: filamentLabel(profile, filaments),
      optionLabel: profileOptionLabel(profile, filaments, printers),
      printerId: profile.printer_id,
      nozzleDiameterMm: profile.nozzle_diameter_mm,
      settings: profile,
    })),
    ...templates.flatMap((template) => template.revisions.map((revision) => ({
      key: `template:${revision.id}`,
      type: 'template' as const,
      sourceId: revision.id,
      label: `${template.name} · template v${revision.version} · ${revision.status.replaceAll('_', ' ')}`,
      optionLabel: `${template.name} · template v${revision.version} · ${revision.status.replaceAll('_', ' ')} · ${scopeLabel(template.printer_id, template.nozzle_diameter_mm, printers)}`,
      printerId: template.printer_id,
      nozzleDiameterMm: template.nozzle_diameter_mm,
      settings: revision.settings,
    }))),
  ], [filaments, printers, profiles, templates])
  const profile = profiles.find((item) => item.id === profileId) ?? profiles[0]
  const validTargets = targets.filter((target) => target.type !== 'profile' || target.sourceId !== profile?.id)
  const target = validTargets.find((item) => item.key === targetKey) ?? validTargets[0]
  const differences = profile && target
    ? getMaterialSettingDifferences(profile, target.settings, catalog, plates)
    : []
  const scopeMismatches = profile && target
    ? getScopeMismatchFields(
      { printerId: profile.printer_id, nozzleDiameterMm: profile.nozzle_diameter_mm },
      { printerId: target.printerId, nozzleDiameterMm: target.nozzleDiameterMm },
    )
    : []
  const leftLabel = profile ? filamentLabel(profile, filaments) : 'Profile'
  const rightLabel = target?.label ?? 'Comparison target'
  const scopeMismatchSummary = scopeMismatches.length === 1
    ? `${scopeMismatches[0]} differs`
    : `${scopeMismatches.join(' and ')} differ`

  const changeProfile = (nextProfileId: string) => {
    setProfileId(nextProfileId)
    if (target?.type === 'profile' && target.sourceId === nextProfileId) {
      setTargetKey(targets.find((item) => item.type !== 'profile' || item.sourceId !== nextProfileId)?.key ?? '')
    }
  }

  return (
    <Modal
      title="Compare material settings"
      description="Choose any profile and compare it with another profile or a template revision. Only settings with different values are shown."
      onClose={onClose}
      size="wide"
      footer={<button className="button" type="button" onClick={onClose}>Close comparison</button>}
    >
      <div className="comparison-layout">
        <EditorSection title="Comparison pair" description="The profile is the baseline. Template revisions include both draft and published history.">
          <div className="comparison-controls">
            <label>
              Profile
              <select value={profile?.id ?? ''} onChange={(event) => changeProfile(event.target.value)} autoFocus>
                {profiles.map((item) => <option key={item.id} value={item.id}>{profileOptionLabel(item, filaments, printers)}</option>)}
              </select>
            </label>
            <label>
              Compare with
              <select value={target?.key ?? ''} onChange={(event) => setTargetKey(event.target.value)} disabled={!validTargets.length}>
                <optgroup label="Material profiles">
                  {validTargets.filter((item) => item.type === 'profile').map((item) => <option key={item.key} value={item.key}>{item.optionLabel}</option>)}
                </optgroup>
                <optgroup label="Material templates">
                  {validTargets.filter((item) => item.type === 'template').map((item) => <option key={item.key} value={item.key}>{item.optionLabel}</option>)}
                </optgroup>
              </select>
            </label>
          </div>
        </EditorSection>

        {profile && target ? <>
          <div className="comparison-scope-grid" aria-label="Comparison scopes">
            <div className="comparison-scope-card"><span>Profile scope</span><strong>{scopeLabel(profile.printer_id, profile.nozzle_diameter_mm, printers)}</strong></div>
            <div className="comparison-scope-card"><span>{target.type === 'template' ? 'Template scope' : 'Compared profile scope'}</span><strong>{scopeLabel(target.printerId, target.nozzleDiameterMm, printers)}</strong></div>
          </div>
          {scopeMismatches.length ? (
            <div className="comparison-scope-warning" role="alert">
              <AlertTriangle size={19} />
              <span><strong>Scope mismatch: {scopeMismatchSummary}.</strong> Review values in context before copying them between these scopes.</span>
            </div>
          ) : (
            <div className="comparison-scope-match" role="status"><CheckCircle2 size={18} /><span>The printer and nozzle scope match.</span></div>
          )}

          <section className="comparison-results" aria-labelledby="comparison-results-title">
            <header><div><p className="eyebrow">Difference-only view</p><h3 id="comparison-results-title">{differences.length} setting {differences.length === 1 ? 'difference' : 'differences'}</h3></div></header>
            {differences.length ? <div className="comparison-table">
              <div className="comparison-row comparison-row--header" aria-hidden="true"><span>Setting</span><span>{leftLabel}</span><span>{rightLabel}</span></div>
              {differences.map((difference) => <div className="comparison-row" key={difference.key}>
                <div className="comparison-setting"><strong>{difference.label}</strong><small>{difference.key}</small></div>
                <div className="comparison-value"><span>{leftLabel}</span><strong>{difference.leftDisplay}</strong></div>
                <div className="comparison-value"><span>{rightLabel}</span><strong>{difference.rightDisplay}</strong></div>
              </div>)}
            </div> : <div className="comparison-empty"><CheckCircle2 size={22} /><div><strong>No setting differences</strong><p>These two items store equivalent material settings.</p></div></div>}
          </section>
        </> : <div className="comparison-empty"><AlertTriangle size={22} /><div><strong>No comparison target available</strong><p>Add another profile or a template revision to compare with this profile.</p></div></div>}
      </div>
    </Modal>
  )
}
