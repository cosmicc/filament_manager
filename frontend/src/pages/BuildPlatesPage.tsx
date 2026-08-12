import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CheckCircle2, Layers3, RefreshCw, Save, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, BuildPlateSurface, BuildPlateSyncResult, Printer } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime } from '../lib/format'

function syncSummary(result: BuildPlateSyncResult): string {
  const created = result.created_codes.length
    ? `Added ${result.created_codes.join(', ')}.`
    : 'No new build plate sides were found.'
  const active = result.active_surface_code
    ? ` Active side: ${result.active_surface_code}.`
    : ' Moonraker did not report a loaded P-number side mesh.'
  const ignored = result.ignored_profile_count
    ? ` Ignored ${result.ignored_profile_count} non-plate mesh${result.ignored_profile_count === 1 ? '' : 'es'}.`
    : ''
  const unavailable = result.unavailable_codes.length
    ? ` Missing mesh: ${result.unavailable_codes.join(', ')}.`
    : ''
  return `${created} Checked ${result.discovered_codes.length} P-number side meshes.${active}${ignored}${unavailable}`
}

interface SurfaceEditorProps {
  surface: BuildPlateSurface
  active: boolean
  canEdit: boolean
  canSelect: boolean
  pending: boolean
  onSelect: () => void
  onSave: (values: { surface_material: string | null; texture: string | null; notes: string | null }) => void
}

function SurfaceEditor({
  surface,
  active,
  canEdit,
  canSelect,
  pending,
  onSelect,
  onSave,
}: SurfaceEditorProps) {
  const meshStatus = surface.mesh_available === null
    ? 'Not checked'
    : surface.mesh_available
      ? 'Available'
      : 'Unavailable'
  return (
    <section className={`plate-surface${active ? ' plate-surface--active' : ''}`}>
      <header>
        <div>
          <p className="eyebrow">Side {surface.side.toUpperCase()}</p>
          <h3>{surface.surface_code}</h3>
        </div>
        <StatusPill status={active ? 'active' : meshStatus.toLowerCase().replace(' ', '_')} />
      </header>
      <dl className="definition-list definition-list--compact">
        <div><dt>Moonraker mesh</dt><dd>{surface.klipper_mesh_profile}</dd></div>
        <div><dt>Surface material</dt><dd>{surface.surface_material ?? 'Not specified'}</dd></div>
        <div><dt>Finish</dt><dd>{surface.texture ?? 'Not specified'}</dd></div>
        <div><dt>Last checked</dt><dd>{dateTime(surface.last_mesh_checked_at)}</dd></div>
        <div><dt>Last calibrated</dt><dd>{dateTime(surface.last_mesh_calibrated_at)}</dd></div>
      </dl>
      {canSelect ? (
        <button
          className="button button--full"
          disabled={active || pending || surface.mesh_available === false}
          title={surface.mesh_available === false ? 'Synchronize after restoring this Moonraker mesh' : undefined}
          onClick={onSelect}
        >
          <Sparkles size={17} />
          {active ? 'Active side' : `Select ${surface.surface_code}`}
        </button>
      ) : null}
      {canEdit ? (
        <details className="plate-editor">
          <summary>Edit side details</summary>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              const data = new FormData(event.currentTarget)
              const material = String(data.get('surface_material') ?? '').trim()
              const texture = String(data.get('texture') ?? '').trim()
              const notes = String(data.get('notes') ?? '').trim()
              onSave({
                surface_material: material || null,
                texture: texture || null,
                notes: notes || null,
              })
            }}
          >
            <label>Surface material<input name="surface_material" defaultValue={surface.surface_material ?? ''} maxLength={120} placeholder="PEI, PEX, glass…" /></label>
            <label>Finish<select name="texture" defaultValue={surface.texture ?? ''}><option value="">Not specified</option><option value="smooth">Smooth</option><option value="textured">Textured</option></select></label>
            <label>Side notes<textarea name="notes" defaultValue={surface.notes ?? ''} maxLength={4000} rows={2} /></label>
            <button className="button" disabled={pending} type="submit"><Save size={16} /> Save side</button>
          </form>
        </details>
      ) : null}
    </section>
  )
}

export default function BuildPlatesPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const plates = useQuery({
    queryKey: ['plates'],
    queryFn: () => apiFetch<BuildPlate[]>('/build-plates'),
  })
  const printers = useQuery({
    queryKey: ['printers'],
    queryFn: () => apiFetch<Printer[]>('/printers'),
  })
  const [printerId, setPrinterId] = useState('')
  const selectedPrinterId = printerId || printers.data?.[0]?.id || ''
  const selectedPrinter = printers.data?.find((printer) => printer.id === selectedPrinterId)
  const refreshCanonicalState = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['plates'] }),
      client.invalidateQueries({ queryKey: ['printers'] }),
      client.invalidateQueries({ queryKey: ['dashboard'] }),
    ])
  }
  const selectSurface = useMutation({
    mutationFn: ({ plateId, surfaceId }: { plateId: string; surfaceId: string }) =>
      apiFetch(`/build-plates/${plateId}/select`, {
        method: 'POST',
        body: JSON.stringify({ printer_id: selectedPrinterId, surface_id: surfaceId }),
      }),
    onSuccess: refreshCanonicalState,
  })
  const updatePlate = useMutation({
    mutationFn: ({ plate, values }: { plate: BuildPlate; values: Record<string, unknown> }) =>
      apiFetch(`/build-plates/${plate.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ expected_version: plate.record_version, ...values }),
      }),
    onSuccess: refreshCanonicalState,
  })
  const updateSurface = useMutation({
    mutationFn: ({ plate, surface, values }: { plate: BuildPlate; surface: BuildPlateSurface; values: { surface_material: string | null; texture: string | null; notes: string | null } }) =>
      apiFetch(`/build-plates/${plate.id}/surfaces/${surface.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ expected_version: surface.record_version, ...values }),
      }),
    onSuccess: refreshCanonicalState,
  })
  const synchronize = useMutation({
    mutationFn: () =>
      apiFetch<BuildPlateSyncResult>('/build-plates/synchronize', {
        method: 'POST',
        body: JSON.stringify({ printer_id: selectedPrinterId }),
      }),
    onSuccess: refreshCanonicalState,
  })
  const mutationError = synchronize.error ?? selectSurface.error ?? updatePlate.error ?? updateSurface.error

  return (
    <div>
      <PageHeader
        eyebrow="Moonraker surface library"
        title="Build plates"
        description="Track each physical P-number plate and the material, finish, and mesh assigned to each printable side."
        actions={user?.role !== 'viewer' && printers.data?.length ? (
          <>
            <label className="inline-field">
              Printer
              <select value={selectedPrinterId} onChange={(event) => setPrinterId(event.target.value)}>
                {printers.data.map((printer) => (
                  <option key={printer.id} value={printer.id}>{printer.name}</option>
                ))}
              </select>
            </label>
            {user?.role === 'administrator' ? (
              <button className="button button--primary" disabled={synchronize.isPending || !selectedPrinterId} onClick={() => synchronize.mutate()}>
                <RefreshCw size={17} />
                {synchronize.isPending ? 'Synchronizing…' : 'Synchronize with Moonraker'}
              </button>
            ) : null}
          </>
        ) : undefined}
      />
      {synchronize.data ? <p className="success-note plate-sync-note"><CheckCircle2 size={17} /><span>{syncSummary(synchronize.data)}</span></p> : null}
      {mutationError ? <p className="form-error plate-sync-note">{mutationError.message}</p> : null}
      {plates.isLoading ? (
        <LoadingState />
      ) : !plates.data?.length ? (
        <EmptyState icon={Layers3} title="No plates configured" description="Seed P1 through P5, then synchronize to add any later P-number side meshes saved in Moonraker." />
      ) : (
        <section className="plate-grid">
          {plates.data.map((plate) => {
            const activePlate = selectedPrinter?.active_plate_id === plate.id
            return (
              <article className={`plate-tile${activePlate ? ' plate-tile--active' : ''}`} key={plate.id}>
                <div className="plate-illustration plate-illustration--large"><span>{plate.plate_code}</span>{activePlate ? <i><Check size={16} /></i> : null}</div>
                <header>
                  <div><p className="eyebrow">Physical plate {plate.plate_code}</p><h2>{plate.display_name}</h2></div>
                  <StatusPill status={activePlate ? 'active' : plate.status} />
                </header>
                <p className="plate-description">{plate.description ?? 'No plate description has been recorded.'}</p>
                <dl className="definition-list definition-list--compact">
                  <div><dt>Condition</dt><dd>{plate.condition}</dd></div>
                  <div><dt>Product</dt><dd>{[plate.manufacturer, plate.product_name].filter(Boolean).join(' · ') || 'Not specified'}</dd></div>
                  <div><dt>Shape</dt><dd>{plate.shape ?? 'Not specified'}</dd></div>
                  <div><dt>Properties</dt><dd>{[plate.magnetic === true ? 'Magnetic' : null, plate.flexible === true ? 'Flexible' : null].filter(Boolean).join(' · ') || 'Not specified'}</dd></div>
                  <div><dt>Preferred materials</dt><dd>{plate.preferred_materials.join(', ') || 'Not specified'}</dd></div>
                  <div><dt>Maximum bed temperature</dt><dd>{plate.max_bed_temp_c ? `${plate.max_bed_temp_c} °C` : 'Not specified'}</dd></div>
                  <div><dt>Last cleaned</dt><dd>{dateTime(plate.last_cleaned_at)}</dd></div>
                </dl>
                {user?.role !== 'viewer' ? (
                  <details className="plate-editor">
                    <summary>Edit physical plate</summary>
                    <form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); const optional = (key: string) => String(data.get(key) ?? '').trim() || null; const triState = (key: string) => { const value = String(data.get(key) ?? ''); return value === '' ? null : value === 'true' }; updatePlate.mutate({ plate, values: { display_name: String(data.get('display_name') ?? '').trim(), description: optional('description'), manufacturer: optional('manufacturer'), product_name: optional('product_name'), shape: optional('shape'), dimensions_mm: { width: optional('width'), depth: optional('depth'), diameter: optional('diameter'), thickness: optional('thickness') }, magnetic: triState('magnetic'), flexible: triState('flexible'), condition: String(data.get('condition')), status: String(data.get('status')), preferred_materials: String(data.get('preferred_materials') ?? '').split(',').map((item) => item.trim()).filter(Boolean), max_bed_temp_c: optional('max_bed_temp_c'), notes: optional('notes') } }) }}>
                      <label>Name<input name="display_name" defaultValue={plate.display_name} required maxLength={120} /></label>
                      <label>Description<textarea name="description" defaultValue={plate.description ?? ''} maxLength={4000} rows={2} /></label>
                      <label>Manufacturer<input name="manufacturer" defaultValue={plate.manufacturer ?? ''} maxLength={120} /></label>
                      <label>Product or model<input name="product_name" defaultValue={plate.product_name ?? ''} maxLength={160} /></label>
                      <label>Shape<select name="shape" defaultValue={plate.shape ?? ''}><option value="">Not specified</option><option value="rectangular">Rectangular</option><option value="round">Round</option><option value="other">Other</option></select></label>
                      <div className="form-grid">
                        <label>Width (mm)<input name="width" type="number" min="0.01" step="any" defaultValue={plate.dimensions_mm?.width ?? ''} /></label>
                        <label>Depth (mm)<input name="depth" type="number" min="0.01" step="any" defaultValue={plate.dimensions_mm?.depth ?? ''} /></label>
                        <label>Diameter (mm)<input name="diameter" type="number" min="0.01" step="any" defaultValue={plate.dimensions_mm?.diameter ?? ''} /></label>
                        <label>Thickness (mm)<input name="thickness" type="number" min="0.01" step="any" defaultValue={plate.dimensions_mm?.thickness ?? ''} /></label>
                      </div>
                      <label>Magnetic<select name="magnetic" defaultValue={plate.magnetic === null ? '' : String(plate.magnetic)}><option value="">Not specified</option><option value="true">Yes</option><option value="false">No</option></select></label>
                      <label>Flexible<select name="flexible" defaultValue={plate.flexible === null ? '' : String(plate.flexible)}><option value="">Not specified</option><option value="true">Yes</option><option value="false">No</option></select></label>
                      <label>Condition<select name="condition" defaultValue={plate.condition}><option value="new">New</option><option value="good">Good</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="retired">Retired</option></select></label>
                      <label>Status<select name="status" defaultValue={plate.status}><option value="active">Active</option><option value="maintenance">Maintenance</option><option value="retired">Retired</option></select></label>
                      <label>Preferred materials<input name="preferred_materials" defaultValue={plate.preferred_materials.join(', ')} placeholder="PLA, PETG, ASA" /></label>
                      <label>Maximum bed temperature (°C)<input name="max_bed_temp_c" type="number" min="0" max="500" step="any" defaultValue={plate.max_bed_temp_c ?? ''} /></label>
                      <label>Plate notes<textarea name="notes" defaultValue={plate.notes ?? ''} maxLength={4000} rows={2} /></label>
                      <button className="button" disabled={updatePlate.isPending} type="submit"><Save size={16} /> Save plate</button>
                    </form>
                  </details>
                ) : null}
                <div className="plate-surfaces">
                  {plate.surfaces.map((surface) => (
                    <SurfaceEditor
                      key={surface.id}
                      surface={surface}
                      active={selectedPrinter?.active_plate_surface_id === surface.id}
                      canEdit={user?.role !== 'viewer'}
                      canSelect={user?.role !== 'viewer' && Boolean(printers.data?.length)}
                      pending={selectSurface.isPending || updateSurface.isPending}
                      onSelect={() => selectSurface.mutate({ plateId: plate.id, surfaceId: surface.id })}
                      onSave={(values) => updateSurface.mutate({ plate, surface, values })}
                    />
                  ))}
                </div>
              </article>
            )
          })}
        </section>
      )}
    </div>
  )
}
