/* Context providers intentionally colocate their consumer hook and theme catalog. */
/* eslint-disable react-refresh/only-export-components */
import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from 'react'

export type Theme =
  | 'light-navy'
  | 'light-sage'
  | 'light-sand'
  | 'dark-navy'
  | 'dark-indigo'
  | 'dark-graphite'
  | 'dark-forest'
  | 'dark-plum'
  | 'dark-ocean'
  | 'dark-carbon'
  | 'dark-ember'
  | 'dark-arctic'

export interface ThemeOption {
  id: Theme
  label: string
  mode: 'light' | 'dark'
  description: string
  swatches: [string, string, string]
}

export const THEME_OPTIONS: ThemeOption[] = [
  { id: 'light-navy', label: 'Workshop Navy', mode: 'light', description: 'Clean navy and cool workshop blue.', swatches: ['#16324F', '#2F80A5', '#F7FAFC'] },
  { id: 'light-sage', label: 'Coastal Sage', mode: 'light', description: 'Soft sage with deep teal accents.', swatches: ['#1E4D4A', '#4F8A78', '#F4F8F2'] },
  { id: 'light-sand', label: 'Warm Sand', mode: 'light', description: 'Warm parchment with terracotta accents.', swatches: ['#563B2F', '#B85C38', '#FBF6ED'] },
  { id: 'dark-navy', label: 'Workshop Navy Dark', mode: 'dark', description: 'The original deep workshop blue.', swatches: ['#081524', '#55A9CF', '#182D46'] },
  { id: 'dark-indigo', label: 'Midnight Indigo', mode: 'dark', description: 'Inky indigo with electric violet.', swatches: ['#111126', '#8478E8', '#24244A'] },
  { id: 'dark-graphite', label: 'Graphite Amber', mode: 'dark', description: 'Neutral graphite with warm amber.', swatches: ['#151515', '#E5A63B', '#2A2927'] },
  { id: 'dark-forest', label: 'Forest Ember', mode: 'dark', description: 'Deep evergreen with ember orange.', swatches: ['#0C1B18', '#E27A42', '#17352E'] },
  { id: 'dark-plum', label: 'Plum Neon', mode: 'dark', description: 'Dark plum with lively pink-violet.', swatches: ['#1C1020', '#D56BD8', '#3B2142'] },
  { id: 'dark-ocean', label: 'Deep Ocean', mode: 'dark', description: 'Blue-green depths with bright aqua.', swatches: ['#061416', '#38C7C9', '#18383C'] },
  { id: 'dark-carbon', label: 'Carbon Lime', mode: 'dark', description: 'Near-black carbon with crisp lime.', swatches: ['#10120E', '#A8D85E', '#22261C'] },
  { id: 'dark-ember', label: 'Ember Red', mode: 'dark', description: 'Smoldering brown-red with coral.', swatches: ['#180D0D', '#E76F51', '#2D1817'] },
  { id: 'dark-arctic', label: 'Arctic Slate', mode: 'dark', description: 'Cool slate with clear ice blue.', swatches: ['#0D141D', '#74B9E6', '#1D2A38'] },
]

interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)
const validThemes = new Set(THEME_OPTIONS.map((option) => option.id))

function initialTheme(): Theme {
  const saved = localStorage.getItem('filament-manager-theme')
  if (saved === 'light') return 'light-navy'
  if (saved === 'dark') return 'dark-navy'
  if (saved && validThemes.has(saved as Theme)) return saved as Theme
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark-navy' : 'light-navy'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    const option = THEME_OPTIONS.find((item) => item.id === theme) ?? THEME_OPTIONS[0]
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = option.mode
    localStorage.setItem('filament-manager-theme', theme)
  }, [theme])

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      toggleTheme: () => setTheme((current) => current.startsWith('dark-') ? 'light-navy' : 'dark-navy'),
    }),
    [theme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside ThemeProvider')
  return value
}
