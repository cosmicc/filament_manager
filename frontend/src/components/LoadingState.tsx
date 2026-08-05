export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loading-state" role="status" aria-label={label}>
      <span className="spinner" />
      <span>{label}…</span>
    </div>
  )
}
