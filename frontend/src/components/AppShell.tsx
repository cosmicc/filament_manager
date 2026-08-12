import {
  Activity, Boxes, ChevronLeft, ChevronRight, CircleGauge, FlaskConical,
  Layers3, Library, LogOut, Menu, Moon, PackageOpen, PanelLeftClose, Printer,
  MonitorCog, QrCode, Settings, SlidersHorizontal, Sun, Unplug, X,
} from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { NavLink } from '../context/RouterContext'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'

const primaryNavigation = [
  { to: '/', label: 'Dashboard', icon: CircleGauge },
  { to: '/spools', label: 'Spools', icon: Boxes },
  { to: '/filaments', label: 'Filaments', icon: PackageOpen },
  { to: '/profiles', label: 'Profiles', icon: SlidersHorizontal },
  { to: '/templates', label: 'Templates', icon: Library },
  { to: '/calibration', label: 'Calibration', icon: FlaskConical },
  { to: '/plates', label: 'Build plates', icon: Layers3 },
  { to: '/printers', label: 'Printers', icon: Printer },
  { to: '/labels', label: 'Labels', icon: QrCode },
]

const secondaryNavigation = [
  { to: '/integrations', label: 'Integrations', icon: Unplug },
  { to: '/workstations', label: 'Cura workstations', icon: MonitorCog },
  { to: '/activity', label: 'Activity', icon: Activity },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const navItems = (items: typeof primaryNavigation) => items.map(({ to, label, icon: Icon }) => (
    <NavLink
      key={to}
      to={to}
      end={to === '/'}
      className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`}
      onClick={() => setMobileOpen(false)}
      title={collapsed ? label : undefined}
    >
      <Icon size={19} />
      <span>{label}</span>
    </NavLink>
  ))

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
          <div>{navItems(primaryNavigation)}</div>
          <div className="nav-divider" />
          <div>{navItems(secondaryNavigation)}</div>
        </nav>
        <div className="sidebar__footer">
          <button className="nav-item" onClick={toggleTheme} title={collapsed ? `Use ${theme === 'light' ? 'dark' : 'light'} theme` : undefined}>
            {theme === 'light' ? <Moon size={19} /> : <Sun size={19} />}
            <span>{theme === 'light' ? 'Dark theme' : 'Light theme'}</span>
          </button>
          <div className="account">
            <span className="account__avatar">{user?.display_name.slice(0, 1).toUpperCase()}</span>
            <span className="account__copy"><strong>{user?.display_name}</strong><small>{user?.role}</small></span>
            <button className="icon-button" onClick={() => void logout()} aria-label="Sign out"><LogOut size={18} /></button>
          </div>
          <button className="sidebar__collapse" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
            {collapsed ? <ChevronRight size={18} /> : <><PanelLeftClose size={18} /><span>Collapse</span><ChevronLeft size={16} /></>}
          </button>
        </div>
      </aside>
      <div className="app-content">
        <header className="mobile-topbar">
          <button className="icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={22} /></button>
          <span><strong>Filament</strong> Manager</span>
          <button className="icon-button" onClick={toggleTheme} aria-label="Toggle color theme">{theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}</button>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  )
}
