import type { MaterialProfile, MaterialSettings } from '../api/types'
import { compactNumber } from './format'

export type Hardness = NonNullable<MaterialSettings['shore_hardness']>

/** MacLellan Rubber's published comparison table, not an exact material conversion.
 * https://maclellanrubber.com/blog/article/rubber-shore-hardness-scales
 * Interpolate only within published A 30–100 / D 6–58; never display extrapolations.
 */
export const hardnessOverlap = [
  [30, 6], [35, 7], [40, 8], [45, 10], [50, 12], [55, 14], [60, 16],
  [65, 19], [70, 22], [75, 25], [80, 29], [85, 33], [90, 39], [95, 46], [100, 58],
] as const

/** Estimate the opposite scale only where the published reference has paired values. */
export function oppositeHardness(hardness: Hardness): number | null {
  const value = Number(hardness.value)
  const source = hardness.scale === 'A' ? 0 : 1
  const target = 1 - source
  if (!Number.isFinite(value) || value < hardnessOverlap[0][source] || value > hardnessOverlap[hardnessOverlap.length - 1][source]) return null
  for (let index = 1; index < hardnessOverlap.length; index++) {
    const lower = hardnessOverlap[index - 1]
    const upper = hardnessOverlap[index]
    if (value <= upper[source]) return lower[target] + (value - lower[source]) * (upper[target] - lower[target]) / (upper[source] - lower[source])
  }
  return null
}

/** Keep the declared measurement first and visibly mark any derived estimate. */
export function formatHardness(hardness: Hardness | null | undefined): string {
  if (!hardness) return 'Not set'
  const opposite = oppositeHardness(hardness)
  return `${compactNumber(hardness.value, 2)}${hardness.scale}${opposite === null ? '' : ` (≈${compactNumber(opposite, 0)}${hardness.scale === 'A' ? 'D' : 'A'})`}`
}

/** A common approximate ordering coordinate; outside overlap only ordering is extended. */
export function hardnessRank(hardness: Hardness): number {
  const value = Number(hardness.value)
  if (hardness.scale === 'D') return value
  return oppositeHardness(hardness) ?? 6 * value / 30
}

/** Group current scopes once for catalog summaries and deterministic approximate sorting. */
export function hardnessByFilament(profiles: MaterialProfile[]): Map<string, { label: string; rank: number | null }> {
  const grouped = new Map<string, { labels: Set<string>; ranks: number[] }>()
  for (const profile of profiles) {
    const entry = grouped.get(profile.filament_product_id) ?? { labels: new Set<string>(), ranks: [] }
    entry.labels.add(formatHardness(profile.shore_hardness))
    if (profile.shore_hardness) entry.ranks.push(hardnessRank(profile.shore_hardness))
    grouped.set(profile.filament_product_id, entry)
  }
  return new Map([...grouped].map(([id, entry]) => [id, { label: [...entry.labels].join(' / '), rank: entry.ranks.length ? Math.min(...entry.ranks) : null }]))
}
