import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronRight, FlaskConical, Play, RefreshCw, Send } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { ApiClientError, apiFetch } from '../api/client'
import type { BuildPlate, Calibration, CalibrationStep, Filament, Printer } from '../api/types'
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

function CreateCalibrationModal({ filaments, printers, plates, onClose }: { filaments: Filament[]; printers: Printer[]; plates: BuildPlate[]; onClose: () => void }) {
  const client = useQueryClient()
  const [filamentId, setFilamentId] = useState(filaments[0]?.id ?? '')
  const [printerId, setPrinterId] = useState(printers[0]?.id ?? '')
  const [plateId, setPlateId] = useState(plates[0]?.id ?? '')
  const [nozzle, setNozzle] = useState(printers[0]?.nozzle_diameter_mm ?? '0.4')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const mutation = useMutation({ mutationFn: () => apiFetch<Calibration>('/calibrations', { method: 'POST', body: JSON.stringify({ filament_product_id: filamentId, printer_id: printerId, nozzle_diameter_mm: nozzle, build_plate_id: plateId || null, notes: notes || null }) }), onSuccess: async () => { await client.invalidateQueries({ queryKey: ['calibrations'] }); onClose() }, onError: (caught) => setError(caught instanceof Error ? caught.message : 'Could not start calibration') })
  return <Modal title="Start calibration" description="Choose the exact material and printer context before printing any test artifacts." onClose={onClose} footer={<><button className="button" onClick={onClose}>Cancel</button><button form="create-calibration" className="button button--primary" disabled={mutation.isPending || !filamentId || !printerId}>Start six-step workflow</button></>}><form id="create-calibration" className="form-stack" onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}><label>Filament product<select value={filamentId} onChange={(event) => setFilamentId(event.target.value)} required>{filaments.map((item) => <option key={item.id} value={item.id}>{item.vendor_name} {item.material_type} · {item.color_name}</option>)}</select></label><div className="form-grid"><label>Printer<select value={printerId} onChange={(event) => { const id = event.target.value; setPrinterId(id); setNozzle(printers.find((item) => item.id === id)?.nozzle_diameter_mm ?? '0.4') }} required>{printers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Nozzle diameter<div className="input-suffix"><input type="number" min="0.1" step="0.1" value={nozzle} onChange={(event) => setNozzle(event.target.value)} required /><span>mm</span></div></label></div><label>Starting build plate<select value={plateId} onChange={(event) => setPlateId(event.target.value)}><option value="">No plate selected</option>{plates.map((item) => <option key={item.id} value={item.id}>{item.plate_code} · {item.display_name}</option>)}</select></label><label>Operator notes <span className="label-optional">Optional</span><textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>{error && <p className="form-error">{error}</p>}</form></Modal>
}

function StepEditor({ calibration, step }: { calibration: Calibration; step: CalibrationStep }) {
  const client = useQueryClient()
  const [values, setValues] = useState<Record<string, string | boolean>>({})
  const [notes, setNotes] = useState(step.notes ?? '')
  const [error, setError] = useState('')
  useEffect(() => {
    const populated: Record<string, string | boolean> = {}
    for (const field of resultFields[step.step_key] ?? []) populated[field.key] = field.type === 'checkbox' ? Boolean(step.result[field.key]) : String(step.result[field.key] ?? '')
    setValues(populated)
    setNotes(step.notes ?? '')
  }, [step])
  const invalidate = () => client.invalidateQueries({ queryKey: ['calibrations'] })
  const start = useMutation({ mutationFn: () => apiFetch(`/calibrations/${calibration.id}/steps/${step.step_key}/start`, { method: 'POST' }), onSuccess: invalidate, onError: (caught) => setError(caught instanceof Error ? caught.message : 'Could not start step') })
  const save = useMutation({ mutationFn: ({ complete, repeat }: { complete: boolean; repeat: boolean }) => {
    const result = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== '').map(([key, value]) => [key, typeof value === 'boolean' ? value : Number(value)]))
    return apiFetch(`/calibrations/${calibration.id}/steps/${step.step_key}/result`, { method: 'POST', body: JSON.stringify({ expected_version: step.record_version, result, notes: notes || null, complete, repeat }) })
  }, onSuccess: invalidate, onError: (caught) => setError(caught instanceof ApiClientError ? caught.message : 'Could not save result') })
  if (step.status === 'not_started') return <div className="step-prompt"><p>Record the test conditions and selected result. Later steps stay locked until this required step is complete.</p><button className="button button--primary" onClick={() => start.mutate()} disabled={start.isPending}><Play size={16} /> Start this step</button>{error && <p className="form-error">{error}</p>}</div>
  return <form className="step-form" onSubmit={(event) => { event.preventDefault(); save.mutate({ complete: true, repeat: false }) }}><div className="form-grid">{(resultFields[step.step_key] ?? []).map((field) => field.type === 'checkbox' ? <label className="check-row" key={field.key}><input type="checkbox" checked={Boolean(values[field.key])} onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.checked }))} /><span><strong>{field.label}</strong></span></label> : <label key={field.key}>{field.label}<div className="input-suffix"><input type="number" step="any" value={String(values[field.key] ?? '')} onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))} required={step.required} />{field.unit && <span>{field.unit}</span>}</div></label>)}</div><label>Observations and artifact reference <span className="label-optional">Recommended</span><textarea rows={4} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Visual quality, test range, Cura project, G-code, photo, or print job reference" /></label>{error && <p className="form-error">{error}</p>}<div className="form-actions">{step.status === 'completed' && <button type="button" className="button" onClick={() => save.mutate({ complete: false, repeat: true })}><RefreshCw size={16} /> Repeat and review downstream</button>}<button className="button button--primary" disabled={save.isPending}><Check size={16} /> {step.status === 'completed' ? 'Update result' : 'Complete step'}</button></div></form>
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

  return <div><PageHeader eyebrow="Guided material tuning" title="Calibration" description="A resumable sequence that turns physical test prints into a versioned profile." actions={canEdit ? <button className="button button--primary" onClick={() => setCreating(true)}><FlaskConical size={17} /> New calibration</button> : undefined} />{sessions.isLoading ? <LoadingState /> : !sessions.data?.length ? <EmptyState icon={FlaskConical} title="No calibration sessions" description="Start with a filament, printer, nozzle, and build plate to create the exact six-step workflow." action={canEdit ? <button className="button button--primary" onClick={() => setCreating(true)}>Start calibration</button> : undefined} /> : selected && selectedStep && <div className="calibration-layout"><aside className="calibration-sidebar"><label>Session<select value={selected.id} onChange={(event) => { setSelectedId(event.target.value); setStepKey('') }}>{sessions.data.map((session) => <option value={session.id} key={session.id}>{filamentName(session.filament_product_id)}</option>)}</select></label><div className="calibration-context"><p className="eyebrow">Current session</p><strong>{filamentName(selected.filament_product_id)}</strong><span>{printers.data?.find((printer) => printer.id === selected.printer_id)?.name ?? 'Printer'} · {selected.nozzle_diameter_mm} mm</span><StatusPill status={selected.status} /></div><ol className="step-list">{selected.steps.sort((a, b) => a.step_order - b.step_order).map((step) => <li key={step.id}><button className={selectedStep.id === step.id ? 'step-button step-button--active' : 'step-button'} onClick={() => setStepKey(step.step_key)}><span>{step.status === 'completed' ? <Check size={15} /> : step.step_order}</span><div><strong>{step.name}</strong><small>{step.required ? 'Required' : 'Optional'} · {step.status.replaceAll('_', ' ')}</small></div><ChevronRight size={16} /></button></li>)}</ol></aside><section className="card calibration-main"><header className="calibration-main__header"><div><p className="eyebrow">Step {selectedStep.step_order} of 6</p><h2>{selectedStep.name}</h2></div><StatusPill status={selectedStep.status} /></header>{canEdit ? <StepEditor calibration={selected} step={selectedStep} /> : <div className="readonly-results"><p>Viewer accounts can inspect recorded results but cannot change a calibration.</p><pre>{JSON.stringify(selectedStep.result, null, 2)}</pre></div>}{ready && <div className="publish-banner"><div><Send size={20} /><span><strong>Mandatory tests are complete</strong><small>Publishing creates a new immutable profile version and queues projections.</small></span></div><button className="button button--primary" onClick={() => publish.mutate()} disabled={publish.isPending}>Publish profile</button></div>}{error && <p className="form-error">{error}</p>}</section></div>}{creating && filaments.data && printers.data && plates.data && <CreateCalibrationModal filaments={filaments.data} printers={printers.data} plates={plates.data} onClose={() => setCreating(false)} />}</div>
}
