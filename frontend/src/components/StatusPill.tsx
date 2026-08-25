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
    'applied',
    'active',
    'validated',
    'healthy',
    'printing',
    'finished',
  ].includes(normalized)
    ? 'success'
    : ['low', 'needs_weighing', 'needs_review', 'pending', 'claimed', 'in_progress', 'ready_to_apply', 'restore_pending', 'restoring', 'not_ready', 'capture_blocked', 'paused', 'starting', 'cancelled'].includes(normalized)
      ? 'warning'
      : ['unavailable', 'offline', 'failed', 'dead', 'empty', 'error', 'invalid', 'restore_failed'].includes(normalized)
        ? 'danger'
        : 'neutral'
  return <span className={`status-pill status-pill--${tone}`}>{label ?? status.replaceAll('_', ' ')}</span>
}
