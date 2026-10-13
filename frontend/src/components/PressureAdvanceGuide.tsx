import { useId, useState } from 'react'
import { pressureAdvanceFromHeight } from '../lib/pressureAdvanceCalculator'
import { EditorSection } from './EditorSection'

/** Read-only preparation guidance and calculator; never sends printer commands. */
export function PressureAdvanceGuide() {
  const [height, setHeight] = useState('')
  const resultId = useId()
  const result = pressureAdvanceFromHeight(height)
  const invalid = height !== '' && result === null
  return <EditorSection title="Pressure Advance preparation and calculator" description="Run the Klipper Prep PA macro before the Pressure Advance test print.">
    <p>Use a smooth factor of <strong>0.020</strong> for the test print and all filaments.</p>
    <p><strong>PA = START + (Height × FACTOR)</strong><br />START is always 0; FACTOR is always 0.020. Height is the good height, measured in millimeters on the PA test print.</p>
    <div className="form-grid">
      <label>Good height (mm)<input type="number" min="0" max="100" step="0.01" value={height} onChange={(event) => setHeight(event.target.value)} aria-invalid={invalid || undefined} aria-describedby={resultId} placeholder="Measured test height" /></label>
      <div><span className="field-help">Calculated Pressure Advance</span><p id={resultId} role="status">{invalid ? 'Enter a height from 0 to 100 mm with up to two decimal places.' : result === null ? 'Enter the measured height to calculate PA.' : <><strong>PA = {result}</strong><br /><small>0 + ({height} × 0.020) = {result}</small></>}</p></div>
    </div>
    <small className="field-help">Enter the calculated PA in the test result below, then save it through the normal calibration workflow.</small>
  </EditorSection>
}
