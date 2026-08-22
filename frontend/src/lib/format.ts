export function grams(value: string | number | null | undefined, precision = 0): string {
  if (value == null) return '—'
  return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: precision })} g`
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
    maximumFractionDigits,
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
  const fixed = numeric.toFixed(maximumFractionDigits)
  return fixed.includes('.') ? fixed.replace(/0+$/, '').replace(/\.$/, '') : fixed
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return 'Never'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

export function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}
