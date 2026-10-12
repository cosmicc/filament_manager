import { useState } from 'react'
import { hardnessOverlap } from '../lib/shoreHardness'
import { Modal } from './Modal'

/** Local, accessible reference; no external assets or third-party scripts are loaded. */
export function ShoreHardnessReference() {
  const [open, setOpen] = useState(false)
  return <>
    <button type="button" className="button button--small" onClick={() => setOpen(true)}>Shore hardness reference</button>
    {open ? <Modal title="Shore hardness reference" onClose={() => setOpen(false)}>
      <div className="editor-form shore-hardness-reference">
      <p>Shore hardness measures resistance to indentation. A suits flexible elastomers; D suits harder elastomers and rigid plastics. Both run from 0 to 100. A higher number is harder within the same scale.</p>
      <div className="table-card shore-hardness-table"><table><caption>Typical hardness ranges</caption><thead><tr><th>Scale / range</th><th>General feel</th></tr></thead><tbody>
        <tr><td>A 0–40</td><td>Soft rubber</td></tr><tr><td>A 40–70</td><td>Medium rubber</td></tr><tr><td>A 70–95</td><td>Firm rubber / elastomer</td></tr><tr><td>D 45–100</td><td>Hard elastomer through rigid plastic</td></tr>
      </tbody></table></div>
      <div className="table-card shore-hardness-table"><table><caption>Approximate A / D comparison used by this app</caption><thead><tr><th>Shore A</th><th>Shore D (approximate)</th></tr></thead><tbody>{hardnessOverlap.map(([a, d]) => <tr key={a}><td>{a}A</td><td>≈{d}D</td></tr>)}</tbody></table></div>
      <p>Opposite-scale estimates interpolate between these reference points only (30–100A / 6–58D). Outside that interval, only your entered scale is shown. Material formulation and test conditions affect the comparison; use the manufacturer’s measured specification. Hardness does not establish printed-part flexibility or strength.</p>
      <p>Reference table: <a href="https://maclellanrubber.com/blog/article/rubber-shore-hardness-scales" target="_blank" rel="noreferrer">MacLellan Rubber</a>. Estimates may differ between reference charts and materials.</p>
      </div>
    </Modal> : null}
  </>
}
