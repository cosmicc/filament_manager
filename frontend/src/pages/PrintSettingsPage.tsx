import { useQuery } from '@tanstack/react-query'
import { Download, GitCompareArrows, Pencil, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, CuraSettingCatalogItem, Filament, MaterialProfile, MaterialTemplate, Printer } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { FilamentSectionNav } from '../components/FilamentSectionNav'
import { LoadingState } from '../components/LoadingState'
import { MaterialComparisonModal } from '../components/MaterialComparisonModal'
import { PageHeader } from '../components/PageHeader'
import { Link } from '../context/RouterContext'
import { compactNumber } from '../lib/format'

export default function PrintSettingsPage() {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => apiFetch<MaterialProfile[]>('/profiles') })
  const filaments = useQuery({ queryKey: ['filaments'], queryFn: () => apiFetch<Filament[]>('/filaments') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const templates = useQuery({ queryKey: ['material-templates'], queryFn: () => apiFetch<MaterialTemplate[]>('/profiles/templates?include_inactive=true') })
  const catalog = useQuery({ queryKey: ['cura-settings-catalog'], queryFn: () => apiFetch<CuraSettingCatalogItem[]>('/profiles/cura-settings/catalog') })
  const [comparisonProfileId, setComparisonProfileId] = useState<string | null>(null)
  const filamentName = (id: string) => {
    const item = filaments.data?.find((value) => value.id === id)
    return item ? `${item.vendor_name ?? ''} ${item.material_type} · ${item.color_name}`.trim() : 'Unknown filament'
  }
  const printerName = (id: string) => printers.data?.find((value) => value.id === id)?.name ?? 'Unknown printer'

  return <div>
    <FilamentSectionNav />
    <PageHeader
      eyebrow="Filament profiles"
      title="Print settings"
      description="Current slicer-ready settings for each exact filament, printer, and nozzle combination. Every scope inherits from its linked template and retains only explicit filament customizations."
      actions={profiles.data?.length ? <button className="button" onClick={() => setComparisonProfileId(profiles.data[0].id)}><GitCompareArrows size={17} /> Compare settings</button> : undefined}
    />
    {profiles.isLoading ? <LoadingState /> : !profiles.data?.length ? (
      <EmptyState icon={SlidersHorizontal} title="No print settings yet" description="Create a filament from a material template, then add other printer or nozzle scopes from that filament." />
    ) : (
      <div className="table-card"><table><thead><tr><th>Filament product</th><th>Printer / nozzle</th><th>Linked template</th><th>Ownership</th><th>Nozzle / initial bed / bed</th><th>Resolved Cura settings</th><th>Actions</th></tr></thead><tbody>{profiles.data.map((profile) => <tr key={profile.id}><td><strong>{filamentName(profile.filament_product_id)}</strong></td><td>{printerName(profile.printer_id)} · {compactNumber(profile.nozzle_diameter_mm, 1)} mm</td><td>{profile.base_template_name ?? 'Missing'}</td><td>{profile.override_count ? `${profile.override_count} customized` : 'Inherited'}</td><td>{compactNumber(profile.extruder_temp_c, 0)}° / {compactNumber(profile.initial_bed_temp_c, 0)}° / {compactNumber(profile.bed_temp_c, 0)}°</td><td>{Object.keys(profile.cura_settings).length} resolved</td><td><div className="table-actions"><button className="icon-button" onClick={() => setComparisonProfileId(profile.id)} title="Compare material settings" aria-label={`Compare ${filamentName(profile.filament_product_id)} print settings`}><GitCompareArrows size={17} /></button><Link className="icon-button" to={`/filaments/${profile.filament_product_id}`} title="Open filament print settings" aria-label={`Open ${filamentName(profile.filament_product_id)} print settings`}><Pencil size={17} /></Link><a className="icon-button" href={`/api/v1/profiles/${profile.id}/exports/cura`} title="Download Cura material settings" aria-label={`Download ${filamentName(profile.filament_product_id)} Cura settings`}><Download size={17} /></a></div></td></tr>)}</tbody></table></div>
    )}
    {comparisonProfileId && profiles.data ? <MaterialComparisonModal
      profiles={profiles.data}
      templates={templates.data ?? []}
      printers={printers.data ?? []}
      filaments={filaments.data ?? []}
      plates={plates.data ?? []}
      catalog={catalog.data ?? []}
      initialProfileId={comparisonProfileId}
      onClose={() => setComparisonProfileId(null)}
    /> : null}
  </div>
}
