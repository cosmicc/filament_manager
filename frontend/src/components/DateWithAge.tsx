import { dateTime, elapsedTime } from '../lib/format'

/** Display the recorded timestamp with a compact, two-unit relative age. */
export function DateWithAge({ value }: { value: string | null | undefined }) {
  return <>{dateTime(value)}{value && <small className="table-subtext">{elapsedTime(value)}</small>}</>
}
