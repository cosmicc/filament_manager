import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock3, Printer as PrinterIcon, RefreshCw, Save, Wifi } from 'lucide-react'
import { useState } from 'react'
import { apiFetch } from '../api/client'
import type { BuildPlate, Printer, SeedSystemResult } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'
import { dateTime } from '../lib/format'

export default function PrintersPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
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
  const [message, setMessage] = useState('')
  const refreshPrinters = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['printers'] }),
      client.invalidateQueries({ queryKey: ['dashboard'] }),
    ])
  }
  const synchronize = useMutation({
    mutationFn: (printerId: string) => apiFetch<Printer>(`/printers/${printerId}/synchronize-info`, { method: 'POST' }),
    onSuccess: async () => { setMessage('Printer information synchronized from Moonraker and Klipper.'); await refreshPrinters() },
    onError: (error: Error) => setMessage(error.message),
  })
  const update = useMutation({
    mutationFn: ({ printer, form }: { printer: Printer; form: HTMLFormElement }) => {
      const data = new FormData(form)
      const optional = (key: string) => String(data.get(key) ?? '').trim() || null
      return apiFetch<Printer>(`/printers/${printer.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          expected_version: printer.record_version,
          name: String(data.get('name') ?? '').trim(),
          manufacturer: optional('manufacturer'),
          model: optional('model'),
          kinematics: optional('kinematics'),
          nozzle_diameter_mm: String(data.get('nozzle_diameter_mm')),
          nozzle_material: optional('nozzle_material'),
          extruder_type: optional('extruder_type'),
          build_volume: {
            shape: optional('shape'),
            x_mm: optional('x_mm'),
            y_mm: optional('y_mm'),
            z_mm: optional('z_mm'),
            diameter_mm: optional('diameter_mm'),
          },
          notes: optional('notes'),
        }),
      })
    },
    onSuccess: async () => { setMessage('Printer details saved.'); await refreshPrinters() },
    onError: (error: Error) => setMessage(error.message),
  })
  const canSeed = user?.role === 'administrator'

  return (
    <div>
      <PageHeader
        eyebrow="Moonraker context"
        title="Printers"
        description="Canonical printer state without exposing internal service addresses to the browser."
      />
      {message && <div className="deployment-note" role="status">{message}</div>}
      {printers.isLoading ? (
        <LoadingState />
      ) : !printers.data?.length ? (
        <>
          <EmptyState
            icon={PrinterIcon}
            title="No printers configured"
            description="Seed the server-configured Moonraker printer from deployment environment variables."
            action={canSeed ? (
              <button
                className="button button--primary"
                disabled={seedSystem.isPending}
                onClick={() => seedSystem.mutate()}
              >
                <RefreshCw size={17} /> {seedSystem.isPending ? 'Seeding printer' : 'Seed configured printer'}
              </button>
            ) : undefined}
          />
          {seedSystem.isError && <p className="form-error">{seedSystem.error.message}</p>}
        </>
      ) : (
        <section className="printer-grid">
          {printers.data.map((printer) => {
            const plate = plates.data?.find((item) => item.id === printer.active_plate_id)
            return (
              <article className="printer-card card" key={printer.id}>
                <div className="printer-card__hero">
                  <span><PrinterIcon size={28} /></span>
                  <StatusPill status={printer.status} />
                </div>
                <h2>{printer.name}</h2>
                <p className="muted">{[printer.manufacturer, printer.model].filter(Boolean).join(' ') || printer.printer_code} · {printer.nozzle_diameter_mm} mm {printer.nozzle_material ? `${printer.nozzle_material} ` : ''}nozzle</p>
                <dl className="definition-list">
                  <div><dt>Printer type</dt><dd>{printer.kinematics ? `${printer.kinematics} kinematics` : 'Not reported'}{printer.extruder_type ? ` · ${printer.extruder_type}` : ''}</dd></div>
                  <div><dt>Build volume</dt><dd>{printer.build_volume.shape === 'round' ? `Ø ${printer.build_volume.diameter_mm ?? printer.build_volume.x_mm ?? '—'} × ${printer.build_volume.z_mm ?? '—'} mm` : printer.build_volume.x_mm ? `${printer.build_volume.x_mm} × ${printer.build_volume.y_mm ?? '—'} × ${printer.build_volume.z_mm ?? '—'} mm` : 'Not reported'}</dd></div>
                  <div><dt>Klipper</dt><dd>{printer.klipper_version ?? 'Not reported'}</dd></div>
                  <div><dt>Moonraker</dt><dd>{printer.moonraker_version ?? 'Not reported'}</dd></div>
                  <div><dt>Printer host</dt><dd>{printer.host_name ?? 'Not reported'}</dd></div>
                  <div>
                    <dt>Active plate</dt>
                    <dd>{plate ? `${plate.plate_code} - ${plate.display_name}` : 'Not selected'}</dd>
                  </div>
                  <div>
                    <dt><Clock3 size={14} /> Last seen</dt>
                    <dd>{dateTime(printer.last_seen_at)}</dd>
                  </div>
                  <div><dt>Information synchronized</dt><dd>{dateTime(printer.last_info_sync_at)}</dd></div>
                </dl>
                {canSeed && <div className="form-actions"><button className="button button--primary" onClick={() => synchronize.mutate(printer.id)} disabled={synchronize.isPending}><RefreshCw size={16} />{synchronize.isPending ? 'Synchronizing…' : 'Pull from Moonraker'}</button></div>}
                {canSeed && <details className="plate-editor"><summary>Edit printer details</summary><form onSubmit={(event) => { event.preventDefault(); update.mutate({ printer, form: event.currentTarget }) }}>
                  <label>Name<input name="name" defaultValue={printer.name} required maxLength={160} /></label>
                  <label>Manufacturer<input name="manufacturer" defaultValue={printer.manufacturer ?? ''} maxLength={160} /></label>
                  <label>Model<input name="model" defaultValue={printer.model ?? ''} maxLength={160} /></label>
                  <label>Kinematics<input name="kinematics" defaultValue={printer.kinematics ?? ''} maxLength={48} placeholder="delta, cartesian, corexy…" /></label>
                  <label>Nozzle diameter (mm)<input name="nozzle_diameter_mm" type="number" min="0.1" max="10" step="any" defaultValue={printer.nozzle_diameter_mm} required /></label>
                  <label>Nozzle material<input name="nozzle_material" defaultValue={printer.nozzle_material ?? ''} maxLength={96} placeholder="Hardened steel, brass…" /></label>
                  <label>Extruder type<input name="extruder_type" defaultValue={printer.extruder_type ?? ''} maxLength={96} placeholder="Direct drive, Bowden…" /></label>
                  <label>Build shape<select name="shape" defaultValue={printer.build_volume.shape ?? ''}><option value="">Not specified</option><option value="rectangular">Rectangular</option><option value="round">Round</option><option value="other">Other</option></select></label>
                  <div className="form-grid"><label>X (mm)<input name="x_mm" type="number" min="0.01" step="any" defaultValue={printer.build_volume.x_mm ?? ''} /></label><label>Y (mm)<input name="y_mm" type="number" min="0.01" step="any" defaultValue={printer.build_volume.y_mm ?? ''} /></label><label>Z (mm)<input name="z_mm" type="number" min="0.01" step="any" defaultValue={printer.build_volume.z_mm ?? ''} /></label><label>Diameter (mm)<input name="diameter_mm" type="number" min="0.01" step="any" defaultValue={printer.build_volume.diameter_mm ?? ''} /></label></div>
                  <label>Notes<textarea name="notes" defaultValue={printer.notes ?? ''} maxLength={4000} rows={3} /></label>
                  <button className="button" type="submit" disabled={update.isPending}><Save size={16} />{update.isPending ? 'Saving…' : 'Save printer'}</button>
                </form></details>}
                <p className="security-note"><Wifi size={16} /> Connection details remain server-side.</p>
              </article>
            )
          })}
        </section>
      )}
    </div>
  )
}
