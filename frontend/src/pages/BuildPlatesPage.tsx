import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Eraser, History, Layers3, Pencil, Plus, Save, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, BuildPlateMaintenanceEvent, BuildPlateMaintenanceStatus, BuildPlateSurface, Printer } from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime, titleCase } from '../lib/format'

function optional(data: FormData, key: string) {
  return String(data.get(key) ?? '').trim() || null
}

function triState(data: FormData, key: string) {
  const value = String(data.get(key) ?? '')
  return value === '' ? null : value === 'true'
}

function PlateEditorModal({
  plate,
  pending,
  error,
  onClose,
  onSave,
}: {
  plate: BuildPlate
  pending: boolean
  error: string
  onClose: () => void
  onSave: (values: Record<string, unknown>) => void
}) {
  return (
    <Modal
      title={`Edit ${plate.plate_code}`}
      description="Keep the physical plate identity, geometry, condition, and usage guidance together."
      onClose={onClose}
      size="wide"
      footer={(
        <>
          <button className="button" type="button" onClick={onClose}>Cancel</button>
          <button className="button button--primary" form={`edit-plate-${plate.id}`} disabled={pending}>
            <Save size={17} />{pending ? 'Saving…' : 'Save plate'}
          </button>
        </>
      )}
    >
      <form
        id={`edit-plate-${plate.id}`}
        className="editor-form"
        onSubmit={(event) => {
          event.preventDefault()
          const data = new FormData(event.currentTarget)
          onSave({
            display_name: String(data.get('display_name') ?? '').trim(),
            description: optional(data, 'description'),
            manufacturer: optional(data, 'manufacturer'),
            product_name: optional(data, 'product_name'),
            shape: optional(data, 'shape'),
            dimensions_mm: {
              width: optional(data, 'width'),
              depth: optional(data, 'depth'),
              diameter: optional(data, 'diameter'),
              thickness: optional(data, 'thickness'),
            },
            magnetic: triState(data, 'magnetic'),
            flexible: triState(data, 'flexible'),
            condition: String(data.get('condition')),
            status: String(data.get('status')),
            preferred_materials: String(data.get('preferred_materials') ?? '')
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean),
            max_bed_temp_c: optional(data, 'max_bed_temp_c'),
            cleaning_due_after_prints: Number(data.get('cleaning_due_after_prints')),
            cleaning_due_after_days: Number(data.get('cleaning_due_after_days')),
            mesh_due_after_prints: Number(data.get('mesh_due_after_prints')),
            mesh_due_after_days: Number(data.get('mesh_due_after_days')),
            notes: optional(data, 'notes'),
          })
        }}
      >
        <EditorSection title="Identity" description="The labels operators use to recognize this physical plate.">
          <div className="form-grid">
            <label>Name<input name="display_name" defaultValue={plate.display_name} required maxLength={120} autoFocus /></label>
            <label>Manufacturer<input name="manufacturer" defaultValue={plate.manufacturer ?? ''} maxLength={120} /></label>
            <label>Product or model<input name="product_name" defaultValue={plate.product_name ?? ''} maxLength={160} /></label>
            <label className="form-grid__wide">Description<textarea name="description" defaultValue={plate.description ?? ''} maxLength={4000} rows={2} /></label>
          </div>
        </EditorSection>
        <EditorSection title="Geometry" description="Use rectangular dimensions or a round diameter as appropriate.">
          <div className="form-grid">
            <label>Shape<select name="shape" defaultValue={plate.shape ?? ''}><option value="">Not specified</option><option value="rectangular">Rectangular</option><option value="round">Round</option><option value="other">Other</option></select></label>
            <label>Thickness (mm)<input name="thickness" type="number" min="0.01" step="any" defaultValue={plate.dimensions_mm?.thickness ?? ''} /></label>
            <label>Width (mm)<input name="width" type="number" min="0.01" step="any" defaultValue={plate.dimensions_mm?.width ?? ''} /></label>
            <label>Depth (mm)<input name="depth" type="number" min="0.01" step="any" defaultValue={plate.dimensions_mm?.depth ?? ''} /></label>
            <label>Diameter (mm)<input name="diameter" type="number" min="0.01" step="any" defaultValue={plate.dimensions_mm?.diameter ?? ''} /></label>
          </div>
        </EditorSection>
        <EditorSection title="Condition and use" description="Group maintenance state and slicer guidance in one place.">
          <div className="form-grid">
            <label>Magnetic<select name="magnetic" defaultValue={plate.magnetic === null ? '' : String(plate.magnetic)}><option value="">Not specified</option><option value="true">Yes</option><option value="false">No</option></select></label>
            <label>Flexible<select name="flexible" defaultValue={plate.flexible === null ? '' : String(plate.flexible)}><option value="">Not specified</option><option value="true">Yes</option><option value="false">No</option></select></label>
            <label>Condition<select name="condition" defaultValue={plate.condition}><option value="new">New</option><option value="good">Good</option><option value="worn">Worn</option><option value="damaged">Damaged</option><option value="retired">Retired</option></select></label>
            <label>Status<select name="status" defaultValue={plate.status}><option value="active">Active</option><option value="maintenance">Maintenance</option><option value="retired">Retired</option></select></label>
            <label>Preferred materials<input name="preferred_materials" defaultValue={plate.preferred_materials.join(', ')} placeholder="PLA, PETG, ASA" /></label>
            <label>Maximum bed temperature (°C)<input name="max_bed_temp_c" type="number" min="0" max="500" step="any" defaultValue={plate.max_bed_temp_c ?? ''} /></label>
            <label className="form-grid__wide">Plate notes<textarea name="notes" defaultValue={plate.notes ?? ''} maxLength={4000} rows={3} /></label>
          </div>
        </EditorSection>
        <EditorSection title="Maintenance reminders" description="A reminder becomes due when either its print-count or age threshold is reached.">
          <div className="form-grid"><label>Clean every (prints)<input name="cleaning_due_after_prints" type="number" min="1" max="10000" defaultValue={plate.cleaning_due_after_prints} /></label><label>Clean every (days)<input name="cleaning_due_after_days" type="number" min="1" max="3650" defaultValue={plate.cleaning_due_after_days} /></label><label>Mesh every (prints)<input name="mesh_due_after_prints" type="number" min="1" max="10000" defaultValue={plate.mesh_due_after_prints} /></label><label>Mesh every (days)<input name="mesh_due_after_days" type="number" min="1" max="3650" defaultValue={plate.mesh_due_after_days} /></label></div>
        </EditorSection>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
      </form>
    </Modal>
  )
}

function SurfaceEditorModal({
  surface,
  pending,
  error,
  onClose,
  onSave,
}: {
  surface: BuildPlateSurface
  pending: boolean
  error: string
  onClose: () => void
  onSave: (values: { surface_material: string | null; texture: string | null; notes: string | null }) => void
}) {
  return (
    <Modal
      title={`Edit ${surface.surface_code}`}
      description="Describe this printable side without changing its Moonraker mesh identity."
      onClose={onClose}
      footer={(
        <>
          <button className="button" type="button" onClick={onClose}>Cancel</button>
          <button className="button button--primary" form={`edit-surface-${surface.id}`} disabled={pending}>
            <Save size={17} />{pending ? 'Saving…' : 'Save side'}
          </button>
        </>
      )}
    >
      <form
        id={`edit-surface-${surface.id}`}
        className="editor-form"
        onSubmit={(event) => {
          event.preventDefault()
          const data = new FormData(event.currentTarget)
          onSave({
            surface_material: optional(data, 'surface_material'),
            texture: optional(data, 'texture'),
            notes: optional(data, 'notes'),
          })
        }}
      >
        <EditorSection title="Surface identity" description="The side code and mesh name are managed automatically from Moonraker.">
          <dl className="definition-list definition-list--compact">
            <div><dt>Side</dt><dd>{surface.side.toUpperCase()}</dd></div>
            <div><dt>Surface code</dt><dd>{surface.surface_code}</dd></div>
            <div><dt>Moonraker mesh</dt><dd>{surface.klipper_mesh_profile}</dd></div>
          </dl>
        </EditorSection>
        <EditorSection title="Surface details" description="Record the coating, finish, and handling notes operators need.">
          <div className="form-grid">
            <label>Surface material<input name="surface_material" defaultValue={surface.surface_material ?? ''} maxLength={120} placeholder="PEI, PEX, glass…" autoFocus /></label>
            <label>Finish<select name="texture" defaultValue={surface.texture ?? ''}><option value="">Not specified</option><option value="smooth">Smooth</option><option value="textured">Textured</option></select></label>
            <label className="form-grid__wide">Side notes<textarea name="notes" defaultValue={surface.notes ?? ''} maxLength={4000} rows={3} /></label>
          </div>
        </EditorSection>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
      </form>
    </Modal>
  )
}

function SurfaceCard({
  surface,
  active,
  canEdit,
  canSelect,
  pending,
  onEdit,
  onSelect,
}: {
  surface: BuildPlateSurface
  active: boolean
  canEdit: boolean
  canSelect: boolean
  pending: boolean
  onEdit: () => void
  onSelect: () => void
}) {
  const meshStatus = surface.mesh_available === null ? 'Not checked' : surface.mesh_available ? 'Available' : 'Unavailable'
  return (
    <section className={`plate-surface${active ? ' plate-surface--active' : ''}`}>
      <header>
        <div><p className="eyebrow">Side {surface.side.toUpperCase()}</p><h3>{surface.surface_code}</h3></div>
        <StatusPill status={active ? 'active' : meshStatus.toLowerCase().replace(' ', '_')} />
      </header>
      <dl className="definition-list definition-list--compact">
        <div><dt>Moonraker mesh</dt><dd>{surface.klipper_mesh_profile}</dd></div>
        <div><dt>Surface material</dt><dd>{surface.surface_material ?? 'Not specified'}</dd></div>
        <div><dt>Finish</dt><dd>{surface.texture ?? 'Not specified'}</dd></div>
        <div><dt>Completed prints</dt><dd>{surface.completed_print_count.toLocaleString()}</dd></div>
        <div><dt>Last checked</dt><dd>{dateTime(surface.last_mesh_checked_at)}</dd></div>
        <div><dt>Last calibrated</dt><dd>{dateTime(surface.last_mesh_calibrated_at)}</dd></div>
      </dl>
      <div className="plate-surface__actions">
        {canSelect ? (
          <button className="button" disabled={active || pending || surface.mesh_available === false} title={surface.mesh_available === false ? 'This mesh is unavailable in Moonraker' : undefined} onClick={onSelect}>
            <Sparkles size={17} />{active ? 'Active side' : `Select ${surface.surface_code}`}
          </button>
        ) : null}
        {canEdit ? <button className="button" onClick={onEdit}><Pencil size={16} /> Edit side</button> : null}
      </div>
    </section>
  )
}

export default function BuildPlatesPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const [printerId, setPrinterId] = useState('')
  const [editingPlate, setEditingPlate] = useState<BuildPlate | null>(null)
  const [editingSurface, setEditingSurface] = useState<{ plate: BuildPlate; surface: BuildPlateSurface } | null>(null)
  const [historyType, setHistoryType] = useState('')
  const [message, setMessage] = useState('')
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates'), refetchInterval: 15_000 })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers'), refetchInterval: 15_000 })
  const maintenance = useQuery({ queryKey: ['plate-maintenance-status'], queryFn: () => apiFetch<BuildPlateMaintenanceStatus[]>('/build-plates/maintenance/status'), refetchInterval: 15_000 })
  const events = useQuery({ queryKey: ['plate-maintenance-events', historyType], queryFn: () => apiFetch<BuildPlateMaintenanceEvent[]>(`/build-plates/maintenance/events?limit=100${historyType ? `&maintenance_type=${historyType}` : ''}`) })
  const selectedPrinterId = printerId || printers.data?.[0]?.id || ''
  const selectedPrinter = printers.data?.find((printer) => printer.id === selectedPrinterId)
  const refreshCanonicalState = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['plates'] }),
      client.invalidateQueries({ queryKey: ['printers'] }),
      client.invalidateQueries({ queryKey: ['dashboard'] }),
      client.invalidateQueries({ queryKey: ['plate-maintenance-status'] }),
      client.invalidateQueries({ queryKey: ['plate-maintenance-events'] }),
    ])
  }
  const selectSurface = useMutation({
    mutationFn: ({ plateId, surfaceId }: { plateId: string; surfaceId: string }) => apiFetch(`/build-plates/${plateId}/select`, { method: 'POST', body: JSON.stringify({ printer_id: selectedPrinterId, surface_id: surfaceId }) }),
    onSuccess: refreshCanonicalState,
  })
  const updatePlate = useMutation({
    mutationFn: ({ plate, values }: { plate: BuildPlate; values: Record<string, unknown> }) => apiFetch(`/build-plates/${plate.id}`, { method: 'PATCH', body: JSON.stringify({ expected_version: plate.record_version, ...values }) }),
    onSuccess: async () => { setEditingPlate(null); await refreshCanonicalState() },
  })
  const updateSurface = useMutation({
    mutationFn: ({ plate, surface, values }: { plate: BuildPlate; surface: BuildPlateSurface; values: { surface_material: string | null; texture: string | null; notes: string | null } }) => apiFetch(`/build-plates/${plate.id}/surfaces/${surface.id}`, { method: 'PATCH', body: JSON.stringify({ expected_version: surface.record_version, ...values }) }),
    onSuccess: async () => { setEditingSurface(null); await refreshCanonicalState() },
  })
  const addSideB = useMutation({
    mutationFn: (plate: BuildPlate) => apiFetch<BuildPlate>(`/build-plates/${plate.id}/surfaces`, { method: 'POST', body: JSON.stringify({}) }),
    onSuccess: async (plate) => {
      setMessage(`${plate.plate_code} Side B was added. Its mesh remains unavailable until ${plate.plate_code}b exists in Moonraker.`)
      await refreshCanonicalState()
      const sideB = plate.surfaces.find((surface) => surface.side === 'b')
      if (sideB) setEditingSurface({ plate, surface: sideB })
    },
  })
  const recordMaintenance = useMutation({
    mutationFn: ({ plateId, maintenanceType, surfaceId }: { plateId: string; maintenanceType: 'cleaned' | 'mesh_calibrated'; surfaceId?: string }) => apiFetch(`/build-plates/${plateId}/maintenance-events`, { method: 'POST', body: JSON.stringify({ maintenance_type: maintenanceType, surface_id: surfaceId ?? null, notes: null }) }),
    onSuccess: refreshCanonicalState,
  })
  const clearActive = useMutation({ mutationFn: () => apiFetch<{ printer_name: string }>('/build-plates/active/clear', { method: 'POST' }), onSuccess: refreshCanonicalState })
  const mutationError = selectSurface.error ?? updatePlate.error ?? updateSurface.error ?? addSideB.error ?? recordMaintenance.error ?? clearActive.error
  return (
    <div>
      <PageHeader
        eyebrow="Moonraker surface library"
        title="Build plates"
        description="Track each physical P-number plate and the material, finish, and mesh assigned to each printable side."
        actions={printers.data?.length ? (
          <><label className="inline-field">Printer<select value={selectedPrinterId} onChange={(event) => setPrinterId(event.target.value)}>{printers.data.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select></label>{user?.role !== 'viewer' && selectedPrinter?.active_plate_surface_id ? <button className="button" disabled={clearActive.isPending} onClick={() => clearActive.mutate()}><Eraser size={17} /> Clear active side</button> : null}</>
        ) : undefined}
      />
      {message ? <div className="deployment-note" role="status">{message}</div> : null}
      {mutationError ? <p className="form-error plate-sync-note">{mutationError.message}</p> : null}
      {plates.error ? <p className="form-error">{plates.error.message}</p> : null}
      {printers.error ? <p className="form-error">{printers.error.message}</p> : null}
      {plates.isLoading ? <LoadingState /> : !plates.data?.length ? (
        <EmptyState icon={Layers3} title="No plates configured" description="P1 through P5 and later P-number meshes are discovered automatically from the configured Moonraker printer." />
      ) : (
        <section className="plate-list">
          {plates.data.map((plate) => {
            const activePlate = selectedPrinter?.active_plate_id === plate.id
            const due = maintenance.data?.find((item) => item.build_plate_id === plate.id)
            return (
              <article className={`build-plate-card${activePlate ? ' build-plate-card--active' : ''}`} key={plate.id}>
                <div className="build-plate-card__summary">
                  <div className="plate-illustration plate-illustration--summary"><span>{plate.plate_code}</span>{activePlate ? <i><Check size={16} /></i> : null}</div>
                  <div className="build-plate-card__identity">
                    <p className="eyebrow">Physical plate {plate.plate_code}</p>
                    <div className="build-plate-card__title"><h2>{plate.display_name}</h2><StatusPill status={activePlate ? 'active' : plate.status} /></div>
                    <p className="plate-description">{plate.description ?? 'No plate description has been recorded.'}</p>
                    <dl className="plate-facts">
                      <div><dt>Condition</dt><dd>{plate.condition}</dd></div>
                      <div><dt>Product</dt><dd>{[plate.manufacturer, plate.product_name].filter(Boolean).join(' · ') || 'Not specified'}</dd></div>
                      <div><dt>Shape</dt><dd>{plate.shape ?? 'Not specified'}</dd></div>
                      <div><dt>Properties</dt><dd>{[plate.magnetic === true ? 'Magnetic' : null, plate.flexible === true ? 'Flexible' : null].filter(Boolean).join(' · ') || 'Not specified'}</dd></div>
                      <div><dt>Preferred materials</dt><dd>{plate.preferred_materials.join(', ') || 'Not specified'}</dd></div>
                      <div><dt>Maximum bed temperature</dt><dd>{plate.max_bed_temp_c ? `${plate.max_bed_temp_c} °C` : 'Not specified'}</dd></div>
                      <div><dt>Last cleaned</dt><dd>{dateTime(plate.last_cleaned_at)}</dd></div>
                      <div><dt>Cleaning state</dt><dd>{due?.cleaning_due ? 'Due now' : `${due?.cleaning_prints_since ?? 0} prints since cleaning`}</dd></div>
                    </dl>
                    {user?.role !== 'viewer' ? <div className="detail-actions"><button className="button build-plate-card__edit" onClick={() => setEditingPlate(plate)}><Pencil size={16} /> Edit physical plate</button><button className="button" disabled={recordMaintenance.isPending} onClick={() => recordMaintenance.mutate({ plateId: plate.id, maintenanceType: 'cleaned' })}><Check size={16} /> Mark cleaned</button></div> : null}
                  </div>
                </div>
                <div className="plate-surfaces">
                  {plate.surfaces.map((surface) => (
                    <SurfaceCard
                      key={surface.id}
                      surface={surface}
                      active={selectedPrinter?.active_plate_surface_id === surface.id}
                      canEdit={user?.role !== 'viewer'}
                      canSelect={user?.role !== 'viewer' && Boolean(printers.data?.length)}
                      pending={selectSurface.isPending}
                      onEdit={() => setEditingSurface({ plate, surface })}
                      onSelect={() => selectSurface.mutate({ plateId: plate.id, surfaceId: surface.id })}
                    />
                  ))}
                </div>
                {user?.role !== 'viewer' && !plate.surfaces.some((surface) => surface.side === 'b') ? <div className="plate-maintenance-actions"><button className="button" disabled={addSideB.isPending} onClick={() => addSideB.mutate(plate)}><Plus size={16} /> Add Side B</button><span className="muted">Creates {plate.plate_code}b now; Moonraker mesh availability updates automatically.</span></div> : null}
                {user?.role !== 'viewer' ? <div className="plate-maintenance-actions">{plate.surfaces.map((surface) => { const state = due?.surfaces.find((item) => item.surface_id === surface.id); return <button className="button" key={surface.id} disabled={recordMaintenance.isPending} onClick={() => recordMaintenance.mutate({ plateId: plate.id, maintenanceType: 'mesh_calibrated', surfaceId: surface.id })}><Sparkles size={16} /> Mark {surface.surface_code} mesh calibrated{state?.mesh_due ? ' · due' : ''}</button> })}</div> : null}
              </article>
            )
          })}
        </section>
      )}
      <section className="card plate-history"><header className="card__header"><div><p className="eyebrow">Immutable ledger</p><h2><History size={20} /> Maintenance history</h2></div><label className="inline-field">Type<select value={historyType} onChange={(event) => setHistoryType(event.target.value)}><option value="">All</option><option value="cleaned">Cleaned</option><option value="mesh_calibrated">Mesh calibrated</option></select></label></header>{events.isLoading ? <LoadingState /> : events.data?.length ? <div className="mobile-card-list mobile-card-list--always">{events.data.map((event) => { const plate = plates.data?.find((item) => item.id === event.build_plate_id); const surface = plate?.surfaces.find((item) => item.id === event.build_plate_surface_id); return <article className="mobile-data-card" key={event.id}><strong>{plate?.plate_code ?? 'Unknown plate'} · {event.maintenance_type === 'cleaned' ? 'Cleaned' : `${surface?.surface_code ?? 'Side'} mesh calibrated`}</strong><span>{dateTime(event.occurred_at)}</span><small>{event.notes ?? titleCase(event.source)}</small></article> })}</div> : <p className="muted">No maintenance events match this filter.</p>}</section>
      {editingPlate ? <PlateEditorModal plate={editingPlate} pending={updatePlate.isPending} error={updatePlate.error?.message ?? ''} onClose={() => setEditingPlate(null)} onSave={(values) => updatePlate.mutate({ plate: editingPlate, values })} /> : null}
      {editingSurface ? <SurfaceEditorModal surface={editingSurface.surface} pending={updateSurface.isPending} error={updateSurface.error?.message ?? ''} onClose={() => setEditingSurface(null)} onSave={(values) => updateSurface.mutate({ ...editingSurface, values })} /> : null}
    </div>
  )
}
