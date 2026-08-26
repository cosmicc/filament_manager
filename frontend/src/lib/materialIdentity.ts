/** Build the four-part material identity used on filament and spool records. */
export function materialIdentitySummary(material: {
  material_type: string
  color_name: string
  filler: string | null
  finish: string | null
}): string {
  return [
    material.material_type,
    material.color_name,
    material.filler?.trim() || 'No filler',
    material.finish?.trim() || 'Standard finish',
  ].join(' · ')
}
