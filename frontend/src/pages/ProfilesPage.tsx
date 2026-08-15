import { useQuery } from '@tanstack/react-query'
import { Download, GitCompareArrows, Pencil, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type {
  BuildPlate,
  CuraSettingCatalogItem,
  Filament,
  MaterialProfile,
  MaterialTemplate,
  Printer,
} from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { MaterialComparisonModal } from '../components/MaterialComparisonModal'
import { PageHeader } from '../components/PageHeader'
import { Link } from '../context/RouterContext'

export default function ProfilesPage() {
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
    <PageHeader
      eyebrow="Slicer-ready settings"
      title="Material profiles"
      description="Current template-linked filament settings. Direct saves synchronize automatically while immutable history remains available to print records and audits."
      actions={profiles.data?.length ? <button className="button" onClick={() => setComparisonProfileId(profiles.data[0].id)}><GitCompareArrows size={17} /> Compare settings</button> : undefined}
    />
    {profiles.isLoading ? <LoadingState /> : !profiles.data?.length ? (
      <EmptyState icon={SlidersHorizontal} title="No profiles yet" description="Create a filament from a material template or apply a completed calibration." />
    ) : (
      <div className="table-card"><table><thead><tr><th>Filament</th><th>Printer</th><th>Linked template</th><th>Overrides</th><th>Temperatures</th><th>Cura settings</th><th>Actions</th></tr></thead><tbody>{profiles.data.map((profile) => <tr key={profile.id}><td><strong>{filamentName(profile.filament_product_id)}</strong></td><td>{printerName(profile.printer_id)} · {profile.nozzle_diameter_mm} mm</td><td>{profile.base_template_name ?? 'Missing'}</td><td>{profile.override_count ? `${profile.override_count} customized` : 'Inherited'}</td><td>{profile.extruder_temp_c}° / {profile.bed_temp_c}°</td><td>{Object.keys(profile.cura_settings).length} resolved</td><td><div className="table-actions"><button className="icon-button" onClick={() => setComparisonProfileId(profile.id)} title="Compare material settings" aria-label={`Compare ${filamentName(profile.filament_product_id)} profile settings`}><GitCompareArrows size={17} /></button><Link className="icon-button" to={`/filaments/${profile.filament_product_id}`} title="Edit filament and profile settings"><Pencil size={17} /></Link><a className="icon-button" href={`/api/v1/profiles/${profile.id}/exports/cura`} title="Download Cura material settings"><Download size={17} /></a></div></td></tr>)}</tbody></table></div>
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
