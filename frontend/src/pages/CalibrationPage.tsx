import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronRight, FlaskConical, Play, RefreshCw, Send } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { ApiClientError, apiFetch } from '../api/client'
import type { BuildPlate, Calibration, CalibrationStep, Filament, Printer } from '../api/types'
import { EditorSection } from '../components/EditorSection'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { useAuth } from '../context/AuthContext'

const resultFields: Record<string, { key: string; label: string; unit?: string; type?: string }[]> = {
  temperature: [
    { key: 'extruder_temp_c', label: 'Selected extruder temperature', unit: '°C' },
    { key: 'bed_temp_c', label: 'Bed temperature', unit: '°C' },
    { key: 'chamber_temp_c', label: 'Chamber temperature', unit: '°C' },
  ],
  flow: [{ key: 'flow_percent', label: 'Selected flow', unit: '%' }],
  pressure_advance: [{ key: 'pressure_advance', label: 'Pressure advance factor' }],
  retraction: [
    { key: 'retraction_distance_mm', label: 'Retraction distance', unit: 'mm' },
    { key: 'retraction_speed_mm_s', label: 'Retraction speed', unit: 'mm/s' },
  ],
  overhang: [
    { key: 'support_overhang_angle_deg', label: 'Support overhang angle', unit: '°' },
    { key: 'tree_max_branch_angle_deg', label: 'Maximum tree branch angle', unit: '°' },
  ],
  ironing: [
    { key: 'ironing_enabled', label: 'Enable ironing', type: 'checkbox' },
    { key: 'ironing_flow_percent', label: 'Ironing flow', unit: '%' },
    { key: 'ironing_speed_mm_s', label: 'Ironing speed', unit: 'mm/s' },
    { key: 'ironing_line_spacing_mm', label: 'Line spacing', unit: 'mm' },
  ],
}

const dimensionalInputFields = [
  { key: 'design_x_mm', label: 'Recorded design X size' },
  { key: 'measured_x_mm', label: 'Actual measured X size' },
  { key: 'design_y_mm', label: 'Recorded design Y size' },
  { key: 'measured_y_mm', label: 'Actual measured Y size' },
  { key: 'design_z_mm', label: 'Recorded design Z size' },
  { key: 'measured_z_mm', label: 'Actual measured Z size' },
  { key: 'design_hole_mm', label: 'Recorded design hole diameter' },
  { key: 'measured_hole_mm', label: 'Actual measured hole diameter' },
  { key: 'design_shaft_mm', label: 'Recorded design shaft diameter' },
  { key: 'measured_shaft_mm', label: 'Actual measured shaft diameter' },
  { key: 'design_wall_thickness_mm', label: 'Recorded design wall thickness' },
  { key: 'measured_wall_thickness_mm', label: 'Actual measured wall thickness' },
]

function CreateCalibrationModal({ filaments, printers, plates, onClose }: { filaments: Filament[]; printers: Printer[]; plates: BuildPlate[]; onClose: () => void }) {
  const client = useQueryClient()
  const [filamentId, setFilamentId] = useState(filaments[0]?.id ?? '')
  const [printerId, setPrinterId] = useState(printers[0]?.id ?? '')
  const [surfaceId, setSurfaceId] = useState(plates.flatMap((plate) => plate.surfaces)[0]?.id ?? '')
  const [nozzle, setNozzle] = useState(printers[0]?.nozzle_diameter_mm ?? '0.4')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const selectedSurface = plates
    .flatMap((plate) => plate.surfaces)
    .find((surface) => surface.id === surfaceId)
  const mutation = useMutation({
    mutationFn: () => apiFetch<Calibration>('/calibrations', {
      method: 'POST',
      body: JSON.stringify({
        filament_product_id: filamentId,
        printer_id: printerId,
        nozzle_diameter_mm: nozzle,
        build_plate_id: selectedSurface?.build_plate_id ?? null,
        build_plate_surface_id: selectedSurface?.id ?? null,
        notes: notes || null,
      }),
    }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['calibrations'] })
      onClose()
    },
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Could not start calibration'),
  })
  return (
    <Modal
      title="Start calibration"
      description="Choose the exact material, printer, and plate side before printing test artifacts."
      onClose={onClose}
      footer={<><button className="button" onClick={onClose}>Cancel</button><button form="create-calibration" className="button button--primary" disabled={mutation.isPending || !filamentId || !printerId}>Start seven-step workflow</button></>}
    >
      <form id="create-calibration" className="form-stack" onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}>
        <EditorSection title="Material and printer" description="The exact combination this calibration will tune.">
          <div className="form-grid">
            <label className="form-grid__wide">Filament product<select value={filamentId} onChange={(event) => setFilamentId(event.target.value)} required autoFocus>{filaments.map((item) => <option key={item.id} value={item.id}>{item.vendor_name} {item.material_type} · {item.color_name}</option>)}</select></label>
            <label>Printer<select value={printerId} onChange={(event) => { const id = event.target.value; setPrinterId(id); setNozzle(printers.find((item) => item.id === id)?.nozzle_diameter_mm ?? '0.4') }} required>{printers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label>Nozzle diameter<div className="input-suffix"><input type="number" min="0.1" step="0.1" value={nozzle} onChange={(event) => setNozzle(event.target.value)} required /><span>mm</span></div></label>
          </div>
        </EditorSection>
        <EditorSection title="Build surface and notes" description="Choose the surface used for the test artifacts and record any starting context.">
          <div className="form-stack">
            <label>Starting build plate side<select value={surfaceId} onChange={(event) => setSurfaceId(event.target.value)}><option value="">No plate side selected</option>{plates.flatMap((plate) => plate.surfaces.map((surface) => <option key={surface.id} value={surface.id}>{surface.surface_code} · {plate.display_name} · {surface.surface_material ?? 'Surface not specified'}</option>))}</select></label>
            <label>Operator notes <span className="label-optional">Optional</span><textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
          </div>
        </EditorSection>
        {error && <p className="form-error">{error}</p>}
      </form>
    </Modal>
  )
}

function StepEditor({ calibration, step }: { calibration: Calibration; step: CalibrationStep }) {
  const client = useQueryClient()
  const [values, setValues] = useState<Record<string, string | boolean>>({})
  const [notes, setNotes] = useState(step.notes ?? '')
  const [error, setError] = useState('')
  useEffect(() => {
    const populated: Record<string, string | boolean> = {}
    if (step.step_key === 'dimensional') {
      for (const field of dimensionalInputFields) populated[field.key] = String(step.inputs[field.key] ?? '')
    } else {
      for (const field of resultFields[step.step_key] ?? []) populated[field.key] = field.type === 'checkbox' ? Boolean(step.result[field.key]) : String(step.result[field.key] ?? '')
    }
    setValues(populated)
    setNotes(step.notes ?? '')
  }, [step])
  const invalidate = () => client.invalidateQueries({ queryKey: ['calibrations'] })
  const start = useMutation({ mutationFn: () => apiFetch(`/calibrations/${calibration.id}/steps/${step.step_key}/start`, { method: 'POST' }), onSuccess: invalidate, onError: (caught) => setError(caught instanceof Error ? caught.message : 'Could not start step') })
  const save = useMutation({ mutationFn: ({ complete, repeat }: { complete: boolean; repeat: boolean }) => {
    const submitted = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== '').map(([key, value]) => [key, typeof value === 'boolean' ? value : Number(value)]))
    return apiFetch(`/calibrations/${calibration.id}/steps/${step.step_key}/result`, { method: 'POST', body: JSON.stringify({ expected_version: step.record_version, inputs: step.step_key === 'dimensional' ? submitted : {}, result: step.step_key === 'dimensional' ? {} : submitted, notes: notes || null, complete, repeat }) })
  }, onSuccess: invalidate, onError: (caught) => setError(caught instanceof ApiClientError ? caught.message : 'Could not save result') })
  if (step.status === 'not_started') return <div className="step-prompt"><p>Record the test conditions and selected result. Later steps stay locked until this required step is complete.</p><button className="button button--primary" onClick={() => start.mutate()} disabled={start.isPending}><Play size={16} /> Start this step</button>{error && <p className="form-error">{error}</p>}</div>
  const fields = step.step_key === 'dimensional' ? dimensionalInputFields.map((field) => ({ ...field, unit: 'mm' })) : resultFields[step.step_key] ?? []
  return (
    <form className="step-form editor-form" onSubmit={(event) => { event.preventDefault(); save.mutate({ complete: true, repeat: false }) }}>
      <EditorSection title="Test result" description={step.step_key === 'dimensional' ? 'Enter the model dimensions and caliper measurements; corrections are calculated by Filament Manager.' : 'Record the selected value from the printed test artifact.'}>
        <div className="form-grid">
          {fields.map((field) => 'type' in field && field.type === 'checkbox' ? (
            <label className="check-row" key={field.key}><input type="checkbox" checked={Boolean(values[field.key])} onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.checked }))} /><span><strong>{field.label}</strong></span></label>
          ) : (
            <label key={field.key}>{field.label}<div className="input-suffix"><input type="number" min={step.step_key === 'dimensional' ? '0.001' : undefined} step="any" value={String(values[field.key] ?? '')} onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))} required={step.required} />{field.unit && <span>{field.unit}</span>}</div></label>
          ))}
        </div>
        {step.step_key === 'dimensional' && step.status === 'completed' ? <div className="dimensional-results"><div className={step.result.axis_warning || step.result.shaft_warning ? 'warning-note' : 'success-note'}><span><strong>{step.result.correction_classification === 'printer_geometry_review' ? 'Printer geometry review recommended' : 'Material compensation is consistent'}</strong> · No Klipper configuration was changed.</span></div><dl className="definition-list"><div><dt>Cura Horizontal Expansion</dt><dd>{String(step.result.xy_offset)} mm</dd></div><div><dt>Hole Horizontal Expansion</dt><dd>{String(step.result.hole_xy_offset)} mm</dd></div><div><dt>Shaft expansion reference</dt><dd>{String(step.result.shaft_horizontal_expansion_mm)} mm</dd></div><div><dt>Recommended flow</dt><dd>{String(step.result.flow_percent)}%</dd></div><div><dt>Printer X/Y/Z scale review</dt><dd>{String(step.result.printer_x_correction_percent)}% / {String(step.result.printer_y_correction_percent)}% / {String(step.result.printer_z_correction_percent)}%</dd></div><div><dt>Material X/Y/Z shrinkage</dt><dd>{String(step.result.material_shrinkage_x_percent)}% / {String(step.result.material_shrinkage_y_percent)}% / {String(step.result.material_shrinkage_z_percent)}%</dd></div></dl>{step.result.axis_warning ? <p className="warning-note">X and Y expansions differ by {String(step.result.axis_difference_mm)} mm. Check mechanics before applying printer scale correction.</p> : null}{step.result.shaft_warning ? <p className="warning-note">The shaft result differs from the X/Y expansion by {String(step.result.shaft_difference_mm)} mm. Review extrusion and feature-specific behavior.</p> : null}</div> : null}
      </EditorSection>
      <EditorSection title="Observations" description="Keep the visual result and artifact reference with this immutable calibration history.">
        <label>Observations and artifact reference <span className="label-optional">Recommended</span><textarea rows={4} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Visual quality, test range, Cura project, G-code, photo, or print job reference" /></label>
      </EditorSection>
      {error ? <p className="form-error">{error}</p> : null}
      <div className="form-actions">{step.status === 'completed' ? <button type="button" className="button" onClick={() => save.mutate({ complete: false, repeat: true })}><RefreshCw size={16} /> Repeat and review downstream</button> : null}<button className="button button--primary" disabled={save.isPending}><Check size={16} /> {step.status === 'completed' ? 'Update result' : 'Complete step'}</button></div>
    </form>
  )
}

export default function CalibrationPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const sessions = useQuery({ queryKey: ['calibrations'], queryFn: () => apiFetch<Calibration[]>('/calibrations') })
  const filaments = useQuery({ queryKey: ['filaments'], queryFn: () => apiFetch<Filament[]>('/filaments') })
  const printers = useQuery({ queryKey: ['printers'], queryFn: () => apiFetch<Printer[]>('/printers') })
  const plates = useQuery({ queryKey: ['plates'], queryFn: () => apiFetch<BuildPlate[]>('/build-plates') })
  const [selectedId, setSelectedId] = useState('')
  const [stepKey, setStepKey] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const selected = useMemo(() => sessions.data?.find((item) => item.id === selectedId) ?? sessions.data?.[0], [sessions.data, selectedId])
  const selectedStep = selected?.steps.find((item) => item.step_key === stepKey) ?? selected?.steps.find((item) => item.status === 'in_progress') ?? selected?.steps.find((item) => item.status !== 'completed') ?? selected?.steps[0]
  const publish = useMutation({ mutationFn: () => apiFetch(`/calibrations/${selected?.id}/publish-profile`, { method: 'POST' }), onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ['calibrations'] }), client.invalidateQueries({ queryKey: ['profiles'] })]) }, onError: (caught) => setError(caught instanceof Error ? caught.message : 'Could not publish profile') })
  const canEdit = user?.role !== 'viewer'
  const ready = selected?.status === 'ready_to_publish'
  const filamentName = (id: string) => { const item = filaments.data?.find((value) => value.id === id); return item ? `${item.vendor_name ?? ''} ${item.material_type} · ${item.color_name}`.trim() : 'Unknown filament' }
  const plateSideName = (id: string | null) => plates.data
    ?.flatMap((plate) => plate.surfaces)
    .find((surface) => surface.id === id)?.surface_code

  return <div><PageHeader eyebrow="Guided material tuning" title="Calibration" description="A resumable sequence that turns physical test prints into a versioned profile." actions={canEdit ? <button className="button button--primary" onClick={() => setCreating(true)}><FlaskConical size={17} /> New calibration</button> : undefined} />{sessions.isLoading ? <LoadingState /> : !sessions.data?.length ? <EmptyState icon={FlaskConical} title="No calibration sessions" description="Start with a filament, printer, nozzle, and build plate side to create the exact seven-step workflow." action={canEdit ? <button className="button button--primary" onClick={() => setCreating(true)}>Start calibration</button> : undefined} /> : selected && selectedStep && <div className="calibration-layout"><aside className="calibration-sidebar"><label>Session<select value={selected.id} onChange={(event) => { setSelectedId(event.target.value); setStepKey('') }}>{sessions.data.map((session) => <option value={session.id} key={session.id}>{filamentName(session.filament_product_id)}</option>)}</select></label><div className="calibration-context"><p className="eyebrow">Current session</p><strong>{filamentName(selected.filament_product_id)}</strong><span>{printers.data?.find((printer) => printer.id === selected.printer_id)?.name ?? 'Printer'} · {selected.nozzle_diameter_mm} mm</span>{plateSideName(selected.build_plate_surface_id) ? <span>Plate side {plateSideName(selected.build_plate_surface_id)}</span> : null}<StatusPill status={selected.status} /></div><ol className="step-list">{selected.steps.sort((a, b) => a.step_order - b.step_order).map((step) => <li key={step.id}><button className={selectedStep.id === step.id ? 'step-button step-button--active' : 'step-button'} onClick={() => setStepKey(step.step_key)}><span>{step.status === 'completed' ? <Check size={15} /> : step.step_order}</span><div><strong>{step.name}</strong><small>{step.required ? 'Required' : 'Optional'} · {step.status.replaceAll('_', ' ')}</small></div><ChevronRight size={16} /></button></li>)}</ol></aside><section className="card calibration-main"><header className="calibration-main__header"><div><p className="eyebrow">Step {selectedStep.step_order} of 7</p><h2>{selectedStep.name}</h2></div><StatusPill status={selectedStep.status} /></header>{canEdit ? <StepEditor calibration={selected} step={selectedStep} /> : <div className="readonly-results"><p>Viewer accounts can inspect recorded results but cannot change a calibration.</p><pre>{JSON.stringify(selectedStep.result, null, 2)}</pre></div>}{ready && <div className="publish-banner"><div><Send size={20} /><span><strong>Mandatory tests are complete</strong><small>Publishing creates a new immutable profile version and queues projections.</small></span></div><button className="button button--primary" onClick={() => publish.mutate()} disabled={publish.isPending}>Publish profile</button></div>}{error && <p className="form-error">{error}</p>}</section></div>}{creating && filaments.data && printers.data && plates.data && <CreateCalibrationModal filaments={filaments.data} printers={printers.data} plates={plates.data} onClose={() => setCreating(false)} />}</div>
}
