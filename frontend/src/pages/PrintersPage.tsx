import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Printer as PrinterIcon, RefreshCw, Save, Wrench } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, Nozzle, Printer, SeedSystemResult } from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { useAuth } from '../context/AuthContext'
import { Link } from '../context/RouterContext'
import { compactNumber, inputNumber } from '../lib/format'

function optional(data: FormData, key: string) {
  return String(data.get(key) ?? '').trim() || null
}

function PrinterEditorModal({
  printer,
  pending,
  error,
  onClose,
  onSave,
}: {
  printer: Printer
  pending: boolean
  error: string
  onClose: () => void
  onSave: (form: HTMLFormElement) => void
}) {
  return (
    <Modal
      title={`Edit ${printer.name}`}
      description="Manual identity and hardware details stay grouped while Moonraker-owned status fields update automatically."
      onClose={onClose}
      size="wide"
      footer={(
        <>
          <button className="button" type="button" onClick={onClose}>Cancel</button>
          <button className="button button--primary" form={`edit-printer-${printer.id}`} disabled={pending}><Save size={17} />{pending ? 'Saving…' : 'Save printer'}</button>
        </>
      )}
    >
      <form id={`edit-printer-${printer.id}`} className="editor-form" onSubmit={(event) => { event.preventDefault(); onSave(event.currentTarget) }}>
        <EditorSection title="Identity" description="Operator-facing labels and notes are preserved during automatic synchronization.">
          <div className="form-grid">
            <label>Name<input name="name" defaultValue={printer.name} required maxLength={160} autoFocus /></label>
            <label>Manufacturer<input name="manufacturer" defaultValue={printer.manufacturer ?? ''} maxLength={160} /></label>
            <label>Model<input name="model" defaultValue={printer.model ?? ''} maxLength={160} /></label>
            <label className="form-grid__wide">Notes<textarea name="notes" defaultValue={printer.notes ?? ''} maxLength={4000} rows={3} /></label>
          </div>
        </EditorSection>
        <EditorSection title="Hardware" description="Record printer hardware that is not owned by the physical nozzle inventory.">
          <div className="form-grid">
            <label>Kinematics<input name="kinematics" defaultValue={printer.kinematics ?? ''} maxLength={48} placeholder="delta, cartesian, corexy…" /></label>
            <label>Extruder type<input name="extruder_type" defaultValue={printer.extruder_type ?? ''} maxLength={96} placeholder="Direct drive, Bowden…" /></label>
          </div>
          <p className="security-note"><Wrench size={16} /> Nozzle size and material are updated by recording the exact physical nozzle installation on the Nozzles page.</p>
        </EditorSection>
        <EditorSection title="Build volume" description="Use X, Y, and Z for rectangular machines or diameter and Z for round beds.">
          <div className="form-grid">
            <label>Build shape<select name="shape" defaultValue={printer.build_volume.shape ?? ''}><option value="">Not specified</option><option value="rectangular">Rectangular</option><option value="round">Round</option><option value="other">Other</option></select></label>
            <label>X (mm)<input name="x_mm" type="number" min="0.1" step="0.1" defaultValue={inputNumber(printer.build_volume.x_mm, 1)} /></label>
            <label>Y (mm)<input name="y_mm" type="number" min="0.1" step="0.1" defaultValue={inputNumber(printer.build_volume.y_mm, 1)} /></label>
            <label>Z (mm)<input name="z_mm" type="number" min="0.1" step="0.1" defaultValue={inputNumber(printer.build_volume.z_mm, 1)} /></label>
            <label>Diameter (mm)<input name="diameter_mm" type="number" min="0.1" step="0.1" defaultValue={inputNumber(printer.build_volume.diameter_mm, 1)} /></label>
          </div>
        </EditorSection>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
      </form>
    </Modal>
  )
}

export default function PrintersPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const [editing, setEditing] = useState<Printer | null>(null)
  const [message, setMessage] = useState('')
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers'), refetchInterval: 15_000 })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates'), refetchInterval: 15_000 })
  const nozzles = useQuery({ queryKey: ['nozzles'], queryFn: () => apiFetch<Nozzle[]>('/nozzles?include_retired=true'), refetchInterval: 15_000 })
  const seedSystem = useMutation({
    mutationFn: () => apiFetch<SeedSystemResult>('/system/seed', { method: 'POST' }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['printers'] }),
        client.invalidateQueries({ queryKey: ['plates'] }),
        client.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
    },
  })
  const refreshPrinters = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['printers'] }),
      client.invalidateQueries({ queryKey: ['dashboard'] }),
    ])
  }
  const update = useMutation({
    mutationFn: ({ printer, form }: { printer: Printer; form: HTMLFormElement }) => {
      const data = new FormData(form)
      return apiFetch<Printer>(`/printers/${printer.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          expected_version: printer.record_version,
          name: String(data.get('name') ?? '').trim(),
          manufacturer: optional(data, 'manufacturer'),
          model: optional(data, 'model'),
          kinematics: optional(data, 'kinematics'),
          extruder_type: optional(data, 'extruder_type'),
          build_volume: {
            shape: optional(data, 'shape'),
            x_mm: optional(data, 'x_mm'),
            y_mm: optional(data, 'y_mm'),
            z_mm: optional(data, 'z_mm'),
            diameter_mm: optional(data, 'diameter_mm'),
          },
          notes: optional(data, 'notes'),
        }),
      })
    },
    onSuccess: async () => {
      setMessage('Printer details saved.')
      setEditing(null)
      await refreshPrinters()
    },
  })
  const canEdit = user?.role === 'administrator'

  return (
    <div>
      <PageHeader eyebrow="Physical printer context" title="Printers" description="Canonical machine identity, workspace, active plate, and exact installed nozzle." actions={<Link className="button" to="/diagnostics">Open diagnostics</Link>} />
      {message ? <div className="deployment-note" role="status">{message}</div> : null}
      {printers.error ? <p className="form-error">{printers.error.message}</p> : null}
      {printers.isLoading ? <LoadingState /> : !printers.data?.length ? (
        <>
          <EmptyState
            icon={PrinterIcon}
            title="No printers configured"
            description="The server automatically creates the Moonraker printer from deployment environment variables. You can also seed it immediately after first setup."
            action={canEdit ? <button className="button button--primary" disabled={seedSystem.isPending} onClick={() => seedSystem.mutate()}><RefreshCw size={17} /> {seedSystem.isPending ? 'Seeding printer' : 'Seed configured printer'}</button> : undefined}
          />
          {seedSystem.isError ? <p className="form-error">{seedSystem.error.message}</p> : null}
        </>
      ) : (
        <section className="printer-list">
          {printers.data.map((printer) => {
            const plate = plates.data?.find((item) => item.id === printer.active_plate_id)
            const nozzle = nozzles.data?.find((item) => item.id === printer.active_nozzle_id)
            return (
              <article className="printer-card card" key={printer.id}>
                <div className="printer-card__heading">
                  <span className="printer-card__icon"><PrinterIcon size={28} /></span>
                  <div><p className="eyebrow">{printer.printer_code}</p><h2>{printer.name}</h2><p className="muted">{[printer.manufacturer, printer.model].filter(Boolean).join(' ') || 'Manufacturer and model not specified'}</p></div>
                </div>
                <div className="printer-card__details printer-card__details--single">
                  <EditorSection title="Hardware and workspace">
                    <dl className="definition-list">
                      <div><dt>Printer type</dt><dd>{printer.kinematics ? `${printer.kinematics} kinematics` : 'Not reported'}{printer.extruder_type ? ` · ${printer.extruder_type}` : ''}</dd></div>
                      <div><dt>Build volume</dt><dd>{printer.build_volume.shape === 'round' ? `Ø ${compactNumber(printer.build_volume.diameter_mm ?? printer.build_volume.x_mm, 1)} × ${compactNumber(printer.build_volume.z_mm, 1)} mm` : printer.build_volume.x_mm ? `${compactNumber(printer.build_volume.x_mm, 1)} × ${compactNumber(printer.build_volume.y_mm, 1)} × ${compactNumber(printer.build_volume.z_mm, 1)} mm` : 'Not reported'}</dd></div>
                      <div><dt>Active plate</dt><dd>{plate ? `${plate.plate_code} - ${plate.display_name}` : 'Not selected'}</dd></div>
                      <div><dt>Installed nozzle</dt><dd>{nozzle ? `${nozzle.nozzle_code} · ${compactNumber(nozzle.diameter_mm, 1)} mm ${nozzle.material}` : 'No physical nozzle assigned'}</dd></div>
                    </dl>
                  </EditorSection>
                </div>
                <div className="printer-card__footer">
                  <p className="security-note"><Wrench size={16} /> Manage physical installation and usage on <Link to="/nozzles">Nozzles</Link>.</p>
                  {canEdit ? <button className="button" onClick={() => { setEditing(printer); setMessage('') }}><Pencil size={16} /> Edit printer</button> : null}
                </div>
              </article>
            )
          })}
        </section>
      )}
      {editing ? <PrinterEditorModal printer={editing} pending={update.isPending} error={update.error?.message ?? ''} onClose={() => setEditing(null)} onSave={(form) => update.mutate({ printer: editing, form })} /> : null}
    </div>
  )
}
