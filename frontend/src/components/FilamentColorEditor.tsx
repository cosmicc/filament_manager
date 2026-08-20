import type { FilamentColor } from '../api/types'
import { filamentSwatchStyle } from '../lib/colors'
import { ChevronDown } from 'lucide-react'
import { useId, useState } from 'react'

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
  const [open, setOpen] = useState(false)
  const listId = useId()
  const colorOptions = rememberedColors.some((color) => color.normalized_name === 'rainbow')
    ? rememberedColors
    : [...rememberedColors, { id: 'rainbow', name: 'Rainbow', normalized_name: 'rainbow', color_hex: 'E53935', color_mode: 'rainbow' as const, color_hexes: [], record_version: 1 }]
  const selectRemembered = (nextName: string) => {
    onNameChange(nextName)
    const normalized = nextName.normalize('NFKC').trim().toLocaleLowerCase()
    const remembered = colorOptions.find((color) => color.normalized_name === normalized)
    if (!remembered) {
      if (mode === 'rainbow') {
        onModeChange('solid')
        onColorsChange(['808080'])
      }
      return
    }
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
      while (next.length < 1) next.push('808080')
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
      <div className="color-combobox">
        <input
          value={name}
          onChange={(event) => { selectRemembered(event.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          maxLength={96}
          required
          disabled={disabled}
          placeholder="Choose one or type a custom name"
          role="combobox"
          aria-controls={listId}
          aria-expanded={open}
          aria-autocomplete="list"
        />
        <button type="button" aria-label="Show color choices" disabled={disabled} onClick={() => setOpen((current) => !current)}><ChevronDown size={17} /></button>
        {open ? <div className="color-combobox__menu" id={listId} role="listbox">
          {colorOptions.map((color) => <button type="button" role="option" aria-selected={color.normalized_name === name.normalize('NFKC').trim().toLocaleLowerCase()} key={color.id} onClick={() => { selectRemembered(color.name); setOpen(false) }}><span className="filament-swatch" style={filamentSwatchStyle(color.color_mode, color.color_hexes, color.color_hex)} />{color.name}</button>)}
        </div> : null}
      </div>
      <small className="field-help">Choose a remembered color or type any custom color name.</small>
    </label>
    <label>
      Display type
      <select value={mode === 'rainbow' ? 'solid' : mode} onChange={(event) => changeMode(event.target.value as FilamentColorMode)} disabled={disabled || mode === 'rainbow'}>
        <option value="solid">Solid</option>
        <option value="multicolor">Multicolor (1 to 3 colors)</option>
      </select>
    </label>
    {mode === 'multicolor' ? <label>
      Number of colors
      <select
        value={Math.max(1, visibleColors.length)}
        onChange={(event) => {
          const count = Number(event.target.value)
          const next = [...visibleColors]
          while (next.length < count) next.push(next.length === 1 ? 'FFFFFF' : '000000')
          onColorsChange(next.slice(0, count))
        }}
        disabled={disabled}
      >
        <option value="1">1 color</option>
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
