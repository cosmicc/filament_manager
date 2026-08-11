export function StatusPill({ status, label }: { status: string; label?: string }) {
  const normalized = status.toLowerCase().replaceAll(' ', '_')
  const tone = [
    'connected',
    'completed',
    'committed',
    'succeeded',
    'published',
    'in_stock',
    'ready',
    'active',
    'validated',
  ].includes(normalized)
    ? 'success'
    : ['low', 'needs_weighing', 'needs_review', 'pending', 'claimed', 'in_progress'].includes(normalized)
      ? 'warning'
      : ['unavailable', 'failed', 'dead', 'empty', 'error', 'invalid'].includes(normalized)
        ? 'danger'
        : 'neutral'
  return <span className={`status-pill status-pill--${tone}`}>{label ?? status.replaceAll('_', ' ')}</span>
}
