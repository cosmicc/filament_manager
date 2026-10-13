/** Calculate the operator's fixed PA tower recipe without floating-point drift. */
export function pressureAdvanceFromHeight(height: string): string | null {
  if (!/^\d+(?:\.\d{1,2})?$/.test(height)) return null
  const [whole, fraction = ''] = height.split('.')
  const hundredths = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  if (!Number.isSafeInteger(hundredths) || hundredths > 10000) return null
  return (hundredths / 5000).toFixed(4).replace(/\.?0+$/, '') || '0'
}

