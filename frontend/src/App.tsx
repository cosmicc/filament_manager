import { lazy, Suspense, type ComponentType, type LazyExoticComponent, useEffect } from 'react'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/LoadingState'
import { useAuth } from './context/AuthContext'
import { useRouter } from './context/RouterContext'

const ActivityPage = lazy(() => import('./pages/ActivityPage'))
const BuildPlatesPage = lazy(() => import('./pages/BuildPlatesPage'))
const CalibrationPage = lazy(() => import('./pages/CalibrationPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const DiagnosticsPage = lazy(() => import('./pages/DiagnosticsPage'))
const FilamentsPage = lazy(() => import('./pages/FilamentsPage'))
const FilamentDetailPage = lazy(() => import('./pages/FilamentDetailPage'))
const IntegrationsPage = lazy(() => import('./pages/IntegrationsPage'))
const LabelsPage = lazy(() => import('./pages/LabelsPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const NozzlesPage = lazy(() => import('./pages/NozzlesPage'))
const PrintersPage = lazy(() => import('./pages/PrintersPage'))
const PrintHistoryPage = lazy(() => import('./pages/PrintHistoryPage'))
const PasswordChangePage = lazy(() => import('./pages/PasswordChangePage'))
const ProfilesPage = lazy(() => import('./pages/ProfilesPage'))
const TemplatesPage = lazy(() => import('./pages/TemplatesPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const SpoolsPage = lazy(() => import('./pages/SpoolsPage'))
const WorkstationsPage = lazy(() => import('./pages/WorkstationsPage'))

const pages: Record<string, LazyExoticComponent<ComponentType>> = {
  '/': DashboardPage,
  '/spools': SpoolsPage,
  '/filaments': FilamentsPage,
  '/profiles': ProfilesPage,
  '/prints': PrintHistoryPage,
  '/templates': TemplatesPage,
  '/calibration': CalibrationPage,
  '/plates': BuildPlatesPage,
  '/nozzles': NozzlesPage,
  '/printers': PrintersPage,
  '/labels': LabelsPage,
  '/integrations': IntegrationsPage,
  '/diagnostics': DiagnosticsPage,
  '/activity': ActivityPage,
  '/settings': SettingsPage,
  '/workstations': WorkstationsPage,
}

export function App() {
  const { user, loading } = useAuth()
  const { path, navigate } = useRouter()

  const isFilamentDetail = /^\/filaments\/[0-9a-f-]{36}$/i.test(path)

  useEffect(() => {
    if (loading) return
    if (!user && path !== '/login') navigate('/login', true)
    if (user && path === '/login') navigate('/', true)
    if (user && path !== '/login' && !pages[path] && !isFilamentDetail) navigate('/', true)
  }, [isFilamentDetail, loading, navigate, path, user])

  if (loading) return <div className="app-loading"><LoadingState label="Opening Filament Manager" /></div>
  const content = user
    ? user.must_change_password
      ? <PasswordChangePage />
      : (() => { const Page = isFilamentDetail ? FilamentDetailPage : pages[path] ?? DashboardPage; return <AppShell><Page /></AppShell> })()
    : <LoginPage />
  return <Suspense fallback={<div className="app-loading"><LoadingState /></div>}>{content}</Suspense>
}
