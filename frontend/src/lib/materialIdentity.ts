/** Return a meaningful filler while suppressing the implied unfilled state. */
export function explicitFiller(value: string | null): string | null {
  const normalized = value?.trim()
  if (!normalized || ['none', 'no filler'].includes(normalized.toLocaleLowerCase())) return null
  return normalized
}

/** Return a meaningful finish while suppressing the implied standard finish. */
export function explicitFinish(value: string | null): string | null {
  const normalized = value?.trim()
  if (!normalized || ['standard', 'standard finish'].includes(normalized.toLocaleLowerCase())) return null
  return normalized
}

/** Build the concise material identity used on filament and spool records. */
export function materialIdentitySummary(material: {
  material_type: string
  color_name: string
  filler: string | null
  finish: string | null
}): string {
  return [
    material.material_type,
    material.color_name,
    explicitFiller(material.filler),
    explicitFinish(material.finish),
  ].filter(Boolean).join(' · ')
}

/** Build the optional modifier line shown outside the primary identity. */
export function materialModifierSummary(material: {
  filler: string | null
  finish: string | null
}): string | null {
  const summary = [
    explicitFiller(material.filler),
    explicitFinish(material.finish),
  ].filter(Boolean).join(' · ')
  return summary || null
}
