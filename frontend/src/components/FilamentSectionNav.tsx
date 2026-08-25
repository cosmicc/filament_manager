import { NavLink } from '../context/RouterContext'

/** Shared secondary navigation for filament products and their print settings. */
export function FilamentSectionNav() {
  return <nav className="filament-section-nav" aria-label="Filament sections">
    <NavLink to="/filaments" end className={({ isActive }) => `filament-section-nav__item${isActive ? ' filament-section-nav__item--active' : ''}`}>Catalog</NavLink>
    <NavLink to="/filaments/settings" end className={({ isActive }) => `filament-section-nav__item${isActive ? ' filament-section-nav__item--active' : ''}`}>Print settings</NavLink>
  </nav>
}
