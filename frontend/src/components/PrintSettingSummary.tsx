import type { PrintJob } from '../api/types'
import { compactNumber } from '../lib/format'

const facts = [
  ['extruder_temp_c', 'Printing temperature', '°C'],
  ['initial_bed_temp_c', 'Initial build plate temperature', '°C'],
  ['bed_temp_c', 'Build plate temperature', '°C'],
  ['chamber_temp_c', 'Chamber temperature', '°C'],
  ['layer_height_mm', 'Layer height', 'mm'], ['line_width_mm', 'Line width', 'mm'],
  ['print_speed_mm_s', 'Print speed', 'mm/s'], ['flow_percent', 'Flow', '%'],
  ['retraction_distance_mm', 'Retraction distance', 'mm'], ['retraction_speed_mm_s', 'Retraction speed', 'mm/s'],
  ['pressure_advance', 'Pressure advance', 's'],
] as const

/** Distinguish captured app requests from values recorded in the sliced file. */
export function PrintSettingSummary({ job }: { job: PrintJob }) {
  const sources = job.setting_sources ?? {}
  const evidence = (job.inspection?.extracted ?? {}) as Record<string, unknown>
  const low = Number(evidence.minimum_layer_height_mm)
  const high = Number(evidence.maximum_layer_height_mm)
  const observed = Number.isFinite(low) && Number.isFinite(high) && low > 0
  const adaptive = evidence.adaptive_layers_enabled === true || (observed && high - low > 0.0001)
  return <section><p className="eyebrow">Print settings</p><dl className="definition-list">
    <div><dt>Slicer</dt><dd>{[job.slicer, job.slicer_version].filter(Boolean).join(' ') || 'Not recorded'}</dd></div>
    <div><dt>Cura profile used</dt><dd>{job.cura_quality_profile || 'Not recorded'}</dd></div>
    {observed && <div><dt>{adaptive ? 'Adaptive layer heights' : 'Observed layer height'}</dt><dd>{compactNumber(low, 2)}{high !== low ? `–${compactNumber(high, 2)}` : ''} mm</dd></div>}{evidence.initial_layer_height_mm != null && <div><dt>Initial layer height</dt><dd>{compactNumber(String(evidence.initial_layer_height_mm), 2)} mm</dd></div>}{evidence.initial_layer_line_width_percent != null && <div><dt>Initial layer line width</dt><dd>{compactNumber(String(evidence.initial_layer_line_width_percent), 2)}% of normal line width</dd></div>}{facts.map(([key, label, unit]) => <div key={key}><dt>{key === 'layer_height_mm' && adaptive ? 'Nominal layer height (adaptive)' : label}</dt><dd>{job[key] == null ? 'Not recorded' : <>{compactNumber(job[key], 2)} {unit}<small className="table-subtext">{sources[key] === 'captured_profile' ? 'Captured app settings (not measured)' : 'Recorded print evidence'}</small></>}</dd></div>)}
  </dl></section>
}
