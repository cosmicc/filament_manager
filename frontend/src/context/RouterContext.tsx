/* This dependency-free router intentionally colocates its provider, hooks, and links. */
/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  type MouseEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

interface RouterContextValue {
  path: string
  navigate: (path: string, replace?: boolean) => void
}

const RouterContext = createContext<RouterContextValue | null>(null)

function currentPath(): string {
  const path = window.location.pathname.replace(/\/+$/, '')
  return path || '/'
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(currentPath)

  useEffect(() => {
    const update = () => setPath(currentPath())
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])

  const navigate = useCallback((destination: string, replace = false) => {
    const normalized = destination.startsWith('/') ? destination : `/${destination}`
    if (replace) window.history.replaceState(null, '', normalized)
    else window.history.pushState(null, '', normalized)
    setPath(currentPath())
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [])

  const value = useMemo(() => ({ path, navigate }), [path, navigate])
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterContextValue {
  const value = useContext(RouterContext)
  if (!value) throw new Error('useRouter must be used inside RouterProvider')
  return value
}

export function Link({ to, children, className, ...rest }: {
  to: string
  children: ReactNode
  className?: string
  [key: string]: unknown
}) {
  const { navigate } = useRouter()
  function open(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(to)
  }
  return <a href={to} className={className} onClick={open} {...rest}>{children}</a>
}

export function NavLink({ to, children, className, end = false, ...rest }: {
  to: string
  children: ReactNode
  className?: string | ((state: { isActive: boolean }) => string)
  end?: boolean
  [key: string]: unknown
}) {
  const { path } = useRouter()
  const isActive = end ? path === to : path === to || path.startsWith(`${to}/`)
  const resolvedClass = typeof className === 'function' ? className({ isActive }) : className
  return <Link to={to} className={resolvedClass} {...rest}>{children}</Link>
}
