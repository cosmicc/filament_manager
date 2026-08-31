import {
  Activity, Bell, Boxes, ChevronLeft, ChevronRight, CircleGauge, FlaskConical,
  HeartPulse,
  Layers3, Library, Menu, PackageOpen, Printer,
  MonitorCog, QrCode, Settings, Wrench, X, History,
} from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/client'
import type { OperatorNotification } from '../api/types'
import { NavLink, useRouter } from '../context/RouterContext'
import { APP_VERSION } from '../lib/version'

const primaryNavigation = [
  { to: '/', label: 'Dashboard', icon: CircleGauge },
  { to: '/spools', label: 'Spools', icon: Boxes },
  { to: '/filaments', label: 'Filaments', icon: PackageOpen },
  { to: '/templates', label: 'Templates', icon: Library },
  { to: '/calibration', label: 'Calibration', icon: FlaskConical },
  { to: '/plates', label: 'Build plates', icon: Layers3 },
  { to: '/nozzles', label: 'Nozzles', icon: Wrench },
  { to: '/printers', label: 'Printers', icon: Printer },
  { to: '/prints', label: 'Print history', icon: History },
  { to: '/labels', label: 'Labels', icon: QrCode },
]

function NavigationItems({ items, collapsed, close }: { items: typeof primaryNavigation; collapsed: boolean; close: () => void }) {
  return items.map(({ to, label, icon: Icon }) => (
    <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`} onClick={close} title={collapsed ? label : undefined}>
      <Icon size={19} /><span>{label}</span>
    </NavLink>
  ))
}

function NotificationCenter() {
  const [open, setOpen] = useState(false)
  const centerRef = useRef<HTMLDivElement>(null)
  const client = useQueryClient()
  const { navigate } = useRouter()
  const query = useQuery({ queryKey: ['notifications'], queryFn: () => apiFetch<OperatorNotification[]>('/notifications?limit=100'), refetchInterval: 15_000 })
  const unread = query.data?.filter((item) => !item.read).length ?? 0
  const readOne = useMutation({ mutationFn: (id: string) => apiFetch(`/notifications/${id}/read`, { method: 'POST' }), onSuccess: () => client.invalidateQueries({ queryKey: ['notifications'] }) })
  const readAll = useMutation({ mutationFn: () => apiFetch('/notifications/actions/read-all', { method: 'POST' }), onSuccess: () => client.invalidateQueries({ queryKey: ['notifications'] }) })

  useEffect(() => {
    if (!open) return undefined

    function closeOnOutsidePointer(event: PointerEvent) {
      if (event.target instanceof Node && !centerRef.current?.contains(event.target)) {
        setOpen(false)
      }
    }

    document.addEventListener('pointerdown', closeOnOutsidePointer)
    return () => document.removeEventListener('pointerdown', closeOnOutsidePointer)
  }, [open])

  return <div className="notification-center" ref={centerRef}>
    <button className="icon-button notification-button" onClick={() => setOpen((value) => !value)} aria-label={`${unread} unread notifications`} aria-expanded={open}><Bell size={20} />{unread ? <span>{unread > 99 ? '99+' : unread}</span> : null}</button>
    {open ? <section className="notification-panel"><header><div><p className="eyebrow">Workshop events</p><h2>Notifications</h2></div>{unread ? <button className="text-button" onClick={() => readAll.mutate()}>Mark all read</button> : null}</header><div className="notification-list">{query.data?.length ? query.data.map((item) => <button className={`notification-item${item.read ? '' : ' notification-item--unread'}`} key={item.id} onClick={() => { if (!item.read) readOne.mutate(item.id); if (item.action_path) navigate(item.action_path); setOpen(false) }}><span className={`notification-dot notification-dot--${item.severity}`} /><span><strong>{item.title}</strong><small>{item.message}</small>{item.occurrence_count > 1 ? <em>Seen {item.occurrence_count} times</em> : null}</span></button>) : <p className="muted">No operator notifications.</p>}</div></section> : null}
  </div>
}

const secondaryNavigation = [
  { to: '/diagnostics', label: 'Diagnostics', icon: HeartPulse },
  { to: '/workstations', label: 'Cura workstations', icon: MonitorCog },
  { to: '/activity', label: 'Activity', icon: Activity },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className={`app-shell${collapsed ? ' app-shell--collapsed' : ''}`}>
      {mobileOpen && <button className="sidebar-scrim" onClick={() => setMobileOpen(false)} aria-label="Close navigation" />}
      <aside className={`sidebar${mobileOpen ? ' sidebar--mobile-open' : ''}`}>
        <div className="brand">
          <img src="/assets/filament-manager-mark.png" alt="" />
          <div className="brand__copy"><strong>Filament</strong><span>Manager</span></div>
          <button className="icon-button sidebar__mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={20} /></button>
        </div>
        <nav className="sidebar__nav" aria-label="Main navigation">
          <div><NavigationItems items={primaryNavigation} collapsed={collapsed} close={() => setMobileOpen(false)} /></div>
          <div className="nav-divider" />
          <div><NavigationItems items={secondaryNavigation} collapsed={collapsed} close={() => setMobileOpen(false)} /></div>
        </nav>
        <div className="sidebar__footer">
          <div className="sidebar__version" title={`Filament Manager ${APP_VERSION}`}>
            <span>Version</span><strong>v{APP_VERSION}</strong>
          </div>
          <button className="sidebar__collapse" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>
      </aside>
      <div className="app-content">
        <header className="mobile-topbar">
          <button className="icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={22} /></button>
          <span><strong>Filament</strong> Manager</span>
          <div className="mobile-topbar__actions"><NotificationCenter /></div>
        </header>
        <header className="desktop-topbar"><NotificationCenter /></header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  )
}
