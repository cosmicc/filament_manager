import { useId, useState } from 'react'
import type { MaterialSettings } from '../api/types'
import { compactNumber } from '../lib/format'
import { formatHardness, type Hardness } from '../lib/shoreHardness'
import { ShoreHardnessReference } from './ShoreHardnessReference'

/** Treat scale and value as one override, copy, clear, or revert operation. */
export function ShoreHardnessEditor({ value, base, profile, sources, errors }: {
  value: MaterialSettings['shore_hardness']
  base: MaterialSettings['shore_hardness']
  profile: boolean
  sources: { id: string; label: string; hardness: Hardness }[]
  errors: Record<string, string[]>
}) {
  const id = useId()
  const [scale, setScale] = useState<'A' | 'D'>(value?.scale ?? base?.scale ?? 'A')
  const [number, setNumber] = useState(value?.value ?? '')
  const customized = profile && (number === '' ? base != null : base == null || scale !== base.scale || Number(number) !== Number(base.value))
  const messages = Object.entries(errors).filter(([key]) => key === 'shore_hardness' || key.startsWith('shore_hardness.')).flatMap(([, items]) => items)
  const apply = (hardness: MaterialSettings['shore_hardness']) => { setScale(hardness?.scale ?? 'A'); setNumber(hardness?.value ?? '') }
  return <div className={`setting-field${customized ? ' setting-field--customized' : ''}${messages.length ? ' setting-field--invalid' : ''}`}>
    <div className="form-grid">
      <label>Shore hardness scale<select name="shore_hardness_scale" value={scale} onChange={(event) => setScale(event.target.value as 'A' | 'D')} aria-invalid={messages.length ? true : undefined} aria-describedby={messages.length ? `${id}-error` : undefined}><option value="A">Shore A</option><option value="D">Shore D</option></select></label>
      <label>Shore hardness value<input name="shore_hardness_value" type="number" min="0" max="100" step="0.01" value={number} onChange={(event) => setNumber(event.target.value)} placeholder="Not set" aria-invalid={messages.length ? true : undefined} aria-describedby={messages.length ? `${id}-error` : undefined} /></label>
    </div>
    {messages.length ? <div className="field-validation" id={`${id}-error`} role="alert">{messages.map((message, index) => <span key={index}>{message}</span>)}</div> : null}
    {number !== '' ? <p>{formatHardness({ scale, value: number })}</p> : null}
    {profile ? <div className="setting-ownership"><span>{customized ? 'Customized' : 'Inherited'} · Template: {formatHardness(base)}</span>{customized ? <button type="button" className="button button--small" onClick={() => apply(base)}>Revert to Template</button> : null}</div> : number === '' ? <label className="setting-copy-control">Missing value · Copy from another template<select value="" disabled={!sources.length} onChange={(event) => { const source = sources.find((item) => item.id === event.target.value); if (source) apply(source.hardness) }}><option value="">{sources.length ? 'Choose a populated template…' : 'No other active template has a value'}</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.label} · {compactNumber(source.hardness.value, 2)}{source.hardness.scale}</option>)}</select></label> : null}
    <ShoreHardnessReference />
  </div>
}
