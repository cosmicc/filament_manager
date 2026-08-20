import { DatabaseZap, FileSpreadsheet, MonitorCog, Printer } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { NavLink } from '../context/RouterContext'

const integrations = [
  {
    name: 'Spoolman',
    role: 'Printer-facing inventory projection',
    detail: 'Filament Manager remains canonical and repairs the supported Spoolman projection through its REST API.',
    icon: DatabaseZap,
    action: 'Open spool inventory',
    to: '/spools',
  },
  {
    name: 'Moonraker and Klipper',
    role: 'Printer state and guarded physical workflows',
    detail: 'Supported APIs and the reference macro file coordinate active spool, build plate, print preflight, and print history.',
    icon: Printer,
    action: 'Open printer state',
    to: '/printers',
  },
  {
    name: 'Google Sheets',
    role: 'Read-only publication target',
    detail: 'Canonical inventory and calibration data can be published to the protected workbook when configured.',
    icon: FileSpreadsheet,
    action: 'Open publication settings',
    to: '/settings',
  },
  {
    name: 'Cura workstation agent',
    role: 'Outbound-only managed material library',
    detail: 'The paired local agent backs up and atomically synchronizes current templates and profiles after Cura closes.',
    icon: MonitorCog,
    action: 'Manage workstations',
    to: '/workstations',
  },
]

export default function IntegrationsPage() {
  return <div>
    <PageHeader eyebrow="External systems" title="Integrations" description="Understand what each integration owns, how data moves, and where to manage its application-side workflow." />
    <section className="integration-grid">{integrations.map(({ name, role, detail, icon: Icon, action, to }) => <article className="integration-card" key={name}>
      <span className="integration-card__icon"><Icon size={23} /></span>
      <div><h2>{name}</h2><strong>{role}</strong><p>{detail}</p><NavLink className="text-link" to={to}>{action}</NavLink></div>
    </article>)}</section>
  </div>
}
