import { DatabaseZap, FileSpreadsheet, MonitorCog, Printer } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { NavLink } from '../context/RouterContext'

const integrations = [
  {
    name: 'Spoolman',
    role: 'Printer-facing inventory projection',
    detail: 'Filament Manager remains canonical and repairs the supported Spoolman projection through its REST API.',
    icon: DatabaseZap,
  },
  {
    name: 'Moonraker and Klipper',
    role: 'Printer state and guarded physical workflows',
    detail: 'Supported APIs and the reference macro file coordinate active spool, build plate, print preflight, and print history.',
    icon: Printer,
  },
  {
    name: 'Google Sheets',
    role: 'Read-only publication target',
    detail: 'Canonical inventory and calibration data can be published to the protected workbook when configured.',
    icon: FileSpreadsheet,
  },
  {
    name: 'Cura workstation agent',
    role: 'Outbound-only managed material library',
    detail: 'The paired local agent backs up and atomically deploys approved templates and profiles after Cura closes.',
    icon: MonitorCog,
  },
]

export default function IntegrationsPage() {
  return <div>
    <PageHeader eyebrow="External systems" title="Integrations" description="Understand what each integration owns and how data moves without mixing configuration guidance with live diagnostics." actions={<NavLink className="button button--primary" to="/diagnostics">Open diagnostics</NavLink>} />
    <section className="integration-grid">{integrations.map(({ name, role, detail, icon: Icon }) => <article className="integration-card" key={name}>
      <span className="integration-card__icon"><Icon size={23} /></span>
      <div><h2>{name}</h2><strong>{role}</strong><p>{detail}</p></div>
    </article>)}</section>
    <section className="card diagnostic-actions"><div><p className="eyebrow">Operational information</p><h2>Statuses have moved to Diagnostics</h2><p>Connection checks, synchronization freshness, worker heartbeats, queue state, recent errors, recovery validation, and safe projection rebuild controls now live together on the Diagnostics page.</p></div><NavLink className="button" to="/diagnostics">View connection and worker status</NavLink></section>
  </div>
}
