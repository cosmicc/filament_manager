import type { FilamentColor } from '../api/types'
import { filamentSwatchStyle } from '../lib/colors'

export type FilamentColorMode = 'solid' | 'multicolor' | 'rainbow'

export function FilamentColorEditor({
  name,
  mode,
  colorHexes,
  rememberedColors,
  onNameChange,
  onModeChange,
  onColorsChange,
  disabled = false,
}: {
  name: string
  mode: FilamentColorMode
  colorHexes: string[]
  rememberedColors: FilamentColor[]
  onNameChange: (value: string) => void
  onModeChange: (value: FilamentColorMode) => void
  onColorsChange: (value: string[]) => void
  disabled?: boolean
}) {
  const selectRemembered = (nextName: string) => {
    onNameChange(nextName)
    const normalized = nextName.normalize('NFKC').trim().toLocaleLowerCase()
    const remembered = rememberedColors.find((color) => color.normalized_name === normalized)
    if (!remembered) return
    onModeChange(remembered.color_mode ?? 'solid')
    onColorsChange(
      remembered.color_hexes?.length ? remembered.color_hexes : [remembered.color_hex],
    )
  }
  const changeMode = (nextMode: FilamentColorMode) => {
    onModeChange(nextMode)
    if (nextMode === 'solid') onColorsChange([colorHexes[0] ?? '808080'])
    if (nextMode === 'multicolor') {
      const next = colorHexes.slice(0, 3)
      while (next.length < 2) next.push(next.length === 0 ? '808080' : 'FFFFFF')
      onColorsChange(next)
    }
  }
  const setColor = (index: number, value: string) => {
    const next = [...colorHexes]
    next[index] = value.replace('#', '').toUpperCase()
    onColorsChange(next)
  }
  const visibleColors = mode === 'multicolor' ? colorHexes.slice(0, 3) : colorHexes.slice(0, 1)

  return <>
    <label>
      Color name
      <input
        list="filament-color-library"
        value={name}
        onChange={(event) => selectRemembered(event.target.value)}
        maxLength={96}
        required
        disabled={disabled}
        placeholder="Choose one or type a custom name"
      />
      <datalist id="filament-color-library">{rememberedColors.map((color) => <option key={color.id} value={color.name} />)}</datalist>
      <small className="field-help">Choose a remembered color or type any custom color name.</small>
    </label>
    <label>
      Display type
      <select value={mode} onChange={(event) => changeMode(event.target.value as FilamentColorMode)} disabled={disabled}>
        <option value="solid">Solid</option>
        <option value="multicolor">Multicolor (2 or 3 colors)</option>
        <option value="rainbow">Rainbow</option>
      </select>
    </label>
    {mode === 'multicolor' ? <label>
      Number of colors
      <select
        value={Math.max(2, visibleColors.length)}
        onChange={(event) => {
          const count = Number(event.target.value)
          const next = [...visibleColors]
          while (next.length < count) next.push(next.length === 1 ? 'FFFFFF' : '000000')
          onColorsChange(next.slice(0, count))
        }}
        disabled={disabled}
      >
        <option value="2">2 colors</option>
        <option value="3">3 colors</option>
      </select>
    </label> : null}
    {mode !== 'rainbow' ? visibleColors.map((color, index) => <label key={index}>
      {mode === 'solid' ? 'Screen color sample' : `Color ${index + 1}`}
      <input type="color" value={`#${color || '808080'}`} onChange={(event) => setColor(index, event.target.value)} disabled={disabled} />
    </label>) : <div className="setting-field"><span>Rainbow display</span><small className="field-help">The spool swatch uses the full rainbow spectrum.</small></div>}
    <div className="setting-field">
      <span>Preview</span>
      <span className="filament-swatch filament-swatch--large" style={filamentSwatchStyle(mode, colorHexes)} aria-label={`${name || 'Filament'} color preview`} />
    </div>
  </>
}
