export function StatusPill({ status, label }: { status: string; label?: string }) {
  const normalized = status.toLowerCase().replaceAll(' ', '_')
  const tone = ['connected', 'completed', 'succeeded', 'published', 'in_stock', 'ready', 'active'].includes(normalized)
    ? 'success'
    : ['low', 'needs_weighing', 'needs_review', 'pending', 'claimed', 'in_progress'].includes(normalized)
      ? 'warning'
      : ['unavailable', 'failed', 'dead', 'empty', 'error'].includes(normalized)
        ? 'danger'
        : 'neutral'
  return <span className={`status-pill status-pill--${tone}`}>{label ?? status.replaceAll('_', ' ')}</span>
}
