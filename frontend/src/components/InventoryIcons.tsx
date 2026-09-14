/** Small monochrome inventory symbols follow the active navigation color. */
export function NozzleIcon({ size = 19 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true"><path d="M8 3h8v6H8zM6 9h12v6H6zM8 15l3 6h2l3-6M8 5h8M8 7h8" /></svg>
}

export function SpoolNavIcon({ size = 19 }: { size?: number }) {
  return <span className="spool-nav-icon" style={{ width: size, height: size }} aria-hidden="true" />
}
