import type { CSSProperties } from 'react'

type ColorMode = 'solid' | 'multicolor' | 'rainbow'

const rainbow = ['#E53935', '#FB8C00', '#FDD835', '#43A047', '#1E88E5', '#8E24AA']

function normalizedColors(colorHexes: string[] | undefined, fallback: string): string[] {
  const values = colorHexes?.length ? colorHexes : [fallback]
  return values.map((value) => `#${value.replace('#', '')}`)
}

export function filamentSwatchStyle(
  mode: ColorMode | undefined,
  colorHexes: string[] | undefined,
  fallback = '2F80A5',
): CSSProperties {
  const colors = normalizedColors(colorHexes, fallback).slice(0, mode === 'multicolor' ? 3 : 1)
  const primary = colors[0]
  if (!mode || mode === 'solid') return { '--swatch': primary } as CSSProperties
  if (mode === 'rainbow') {
    return {
      '--swatch': rainbow[0],
      '--spool-fill': `conic-gradient(from -45deg, ${[...rainbow, rainbow[0]].join(', ')})`,
    } as CSSProperties
  }
  const stops = colors.flatMap((color, index) => {
    const start = Math.round(index / colors.length * 100)
    const end = Math.round((index + 1) / colors.length * 100)
    return [`${color} ${start}%`, `${color} ${end}%`]
  })
  return {
    '--swatch': primary,
    '--spool-fill': `conic-gradient(${stops.join(', ')})`,
  } as CSSProperties
}
