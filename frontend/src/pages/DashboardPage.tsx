import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Boxes, FlaskConical, Layers3, Scale, Unplug } from 'lucide-react'
import { apiFetch } from '../api/client'
import type { DashboardData } from '../api/types'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { PageHeader } from '../components/PageHeader'
import { StatusPill } from '../components/StatusPill'
import { Link } from '../context/RouterContext'
import { grams, percent } from '../lib/format'

function MetricCard({ icon: Icon, label, value, detail, tone = '' }: {
  icon: typeof Boxes
  label: string
  value: number
  detail: string
  tone?: string
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <span className="metric-card__icon"><Icon size={20} /></span>
      <div><p>{label}</p><strong>{value}</strong><small>{detail}</small></div>
    </article>
  )
}

export default function DashboardPage() {
  const query = useQuery({ queryKey: ['dashboard'], queryFn: () => apiFetch<DashboardData>('/dashboard'), refetchInterval: 30_000 })
  if (query.isLoading) return <LoadingState label="Loading workshop status" />
  if (!query.data) return <EmptyState icon={AlertTriangle} title="Dashboard unavailable" description="The operational overview could not be loaded. Check the application service and try again." action={<button className="button" onClick={() => void query.refetch()}>Try again</button>} />
  const data = query.data
  const connected = data.integrations.filter((item) => item.status === 'connected').length

  return (
    <div>
      <PageHeader eyebrow="Workshop overview" title="Dashboard" description="Inventory confidence, printer context, and integration health at a glance." actions={<Link to="/spools" className="button button--primary"><Scale size={17} /> Record a weight</Link>} />
      <section className="metric-grid" aria-label="Inventory summary">
        <MetricCard icon={Boxes} label="Total spools" value={data.total_spools} detail="Active inventory" />
        <MetricCard icon={Scale} label="Needs weighing" value={data.needs_weighing} detail="Manual check required" tone={data.needs_weighing ? 'metric-card--warning' : ''} />
        <MetricCard icon={AlertTriangle} label="Low or empty" value={data.low_spools + data.empty_spools} detail={`${data.empty_spools} empty`} tone={data.low_spools + data.empty_spools ? 'metric-card--warning' : ''} />
        <MetricCard icon={Unplug} label="Integrations" value={connected} detail={`of ${data.integrations.length} connected`} />
      </section>

      <section className="dashboard-grid">
        <article className="card active-spool-card">
          <header className="card__header"><div><p className="eyebrow">Printing context</p><h2>Active spool</h2></div>{data.active_spool && <StatusPill status={data.active_spool.status} />}</header>
          {data.active_spool ? (
            <div className="active-spool">
              <span className="filament-swatch filament-swatch--large" style={{ '--swatch': `#${data.active_spool.color_hex ?? '2F80A5'}` } as React.CSSProperties} />
              <div className="active-spool__identity"><strong>{data.active_spool.spool_code}</strong><span>{[data.active_spool.vendor_name, data.active_spool.material_type, data.active_spool.color_name].filter(Boolean).join(' · ')}</span></div>
              <div className="remaining-visual"><div className="remaining-visual__labels"><span>{grams(data.active_spool.remaining_mass_effective_g)}</span><strong>{percent(data.active_spool.remaining_percent)}</strong></div><div className="progress"><span style={{ width: `${Math.min(100, Number(data.active_spool.remaining_percent))}%` }} /></div><small>{data.active_spool.weight_confidence} confidence</small></div>
              <Link className="text-link" to="/spools">View inventory <ArrowRight size={15} /></Link>
            </div>
          ) : <EmptyState icon={Boxes} title="No active spool" description="Select a printer spool from Inventory to expose the current printing context." action={<Link className="button" to="/spools">Choose a spool</Link>} />}
        </article>

        <article className="card plate-card">
          <header className="card__header"><div><p className="eyebrow">Printer surface</p><h2>Active build plate</h2></div><Layers3 size={21} /></header>
          {data.active_plate ? <div className="plate-summary"><div className="plate-illustration"><span>{data.active_plate.plate_code}</span></div><strong>{data.active_plate.display_name}</strong><span>{data.active_plate.klipper_mesh_profile}</span><StatusPill status={data.active_plate.condition} /></div> : <EmptyState icon={Layers3} title="No plate selected" description="Select one of the P1–P5 plates for a configured printer." action={<Link className="button" to="/plates">Open plates</Link>} />}
        </article>

        <article className="card integrations-card">
          <header className="card__header"><div><p className="eyebrow">Connected systems</p><h2>Integration health</h2></div><Link to="/integrations" className="text-link">Manage <ArrowRight size={15} /></Link></header>
          <div className="integration-list">{data.integrations.map((integration) => <div key={integration.service} className="integration-row"><span className={`health-dot health-dot--${integration.status}`} /><div><strong>{integration.service}</strong><small>{integration.detail}</small></div><StatusPill status={integration.status} /></div>)}</div>
        </article>

        <article className="card quick-card">
          <header className="card__header"><div><p className="eyebrow">Keep moving</p><h2>Quick actions</h2></div></header>
          <div className="quick-actions"><Link to="/spools"><Scale size={19} /><span><strong>Weigh a spool</strong><small>Record a trusted manual measurement</small></span><ArrowRight size={17} /></Link><Link to="/calibration"><FlaskConical size={19} /><span><strong>Resume calibration</strong><small>Continue the six-step workflow</small></span><ArrowRight size={17} /></Link><Link to="/plates"><Layers3 size={19} /><span><strong>Select build plate</strong><small>Update the active Moonraker surface</small></span><ArrowRight size={17} /></Link></div>
        </article>
      </section>
    </div>
  )
}
