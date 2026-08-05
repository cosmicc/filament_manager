/* Context providers intentionally colocate their consumer hook. */
/* eslint-disable react-refresh/only-export-components */
import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from 'react'

export type Theme = 'light' | 'dark'

interface ThemeContextValue {
  theme: Theme
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function initialTheme(): Theme {
  const saved = localStorage.getItem('filament-manager-theme')
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    localStorage.setItem('filament-manager-theme', theme)
  }, [theme])

  const value = useMemo(
    () => ({ theme, toggleTheme: () => setTheme((current) => (current === 'light' ? 'dark' : 'light')) }),
    [theme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside ThemeProvider')
  return value
}
