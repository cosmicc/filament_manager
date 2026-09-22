export function grams(value: string | number | null | undefined, precision = 0): string {
  if (value == null) return '—'
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: Math.max(0, Math.min(2, precision)) })} g`
}

export function percent(value: string | number | null | undefined): string {
  if (value == null) return '—'
  return `${Math.max(0, Number(value)).toFixed(0)}%`
}

export function compactNumber(
  value: string | number | null | undefined,
  maximumFractionDigits = 1,
): string {
  if (value == null || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return numeric.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: Math.max(0, Math.min(2, maximumFractionDigits)),
  })
}

export function currencyAmount(
  value: string | number | null | undefined,
  currency = 'USD',
): string {
  if (value == null || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric)
  } catch {
    return `${currency} ${numeric.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
  }
}

export function costPerGram(
  value: string | number | null | undefined,
  currency = 'USD',
): string {
  if (value == null || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  if (currency === 'USD') {
    return `${(numeric * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}¢/g`
  }
  return `${currency} ${numeric.toLocaleString(undefined, { maximumFractionDigits: 2 })}/g`
}

export function inputNumber(
  value: string | number | null | undefined,
  maximumFractionDigits = 1,
): string {
  if (value == null || value === '') return ''
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  const fixed = numeric.toFixed(Math.max(0, Math.min(2, maximumFractionDigits)))
  return fixed.includes('.') ? fixed.replace(/0+$/, '').replace(/\.$/, '') : fixed
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return 'Never'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

/** Format a measured duration using its two largest nonzero units. */
export function durationText(value: string | number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value)) || Number(value) < 0) return 'Unavailable'
  let remaining = Math.floor(Number(value))
  const parts: string[] = []
  for (const [label, size] of [['day', 86400], ['hour', 3600], ['minute', 60], ['second', 1]] as const) {
    const count = Math.floor(remaining / size)
    if (count) parts.push(`${count} ${label}${count === 1 ? '' : 's'}`)
    remaining %= size
    if (parts.length === 2) break
  }
  return parts.join(', ') || '0 seconds'
}

/** Express elapsed time using at most two nonzero units without rounding up. */
export function elapsedTime(value: string, now = Date.now()): string {
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return ''
  let seconds = Math.max(0, Math.floor((now - timestamp) / 1000))
  const parts: string[] = []
  for (const [label, size] of [['Week', 604800], ['Day', 86400], ['Hour', 3600], ['Minute', 60]] as const) {
    const count = Math.floor(seconds / size)
    if (count) parts.push(`${count} ${label}${count === 1 ? '' : 's'}`)
    seconds %= size
    if (parts.length === 2) break
  }
  return parts.length ? `${parts.join(', ')} ago` : 'Less than a minute ago'
}

/** Keep stored precision when an operator saves an unchanged rounded control. */
export function preserveUnchangedNumber(value: string, original: string, precision: number): string {
  return Number(value) === Number(inputNumber(original, precision)) ? original : value
}

export function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}
