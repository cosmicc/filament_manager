import type { FilamentColor } from '../api/types'
import { filamentSwatchStyle } from '../lib/colors'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import { Modal } from './Modal'
import { NewItemSelect } from './NewItemSelect'

export type FilamentColorMode = 'solid' | 'multicolor' | 'rainbow'

export function FilamentColorEditor({
  name,
  mode,
  colorHexes,
  colorNames = [],
  onColorNamesChange,
  rememberedColors,
  onNameChange,
  onModeChange,
  onColorsChange,
  validationErrors = {},
  errorIdPrefix = 'filament-color',
  disabled = false,
}: {
  name: string
  mode: FilamentColorMode
  colorHexes: string[]
  colorNames?: string[]
  onColorNamesChange?: (value: string[]) => void
  rememberedColors: FilamentColor[]
  onNameChange: (value: string) => void
  onModeChange: (value: FilamentColorMode) => void
  onColorsChange: (value: string[]) => void
  validationErrors?: Record<string, string[]>
  errorIdPrefix?: string
  disabled?: boolean
}) {
  const [componentTarget, setComponentTarget] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [added, setAdded] = useState<FilamentColor[]>([])
  const colorOptions = [...rememberedColors, ...added.filter((color) => !rememberedColors.some((known) => known.normalized_name === color.normalized_name))]
  const create = useMutation({
    mutationFn: async (data: FormData) => {
      const color = await apiFetch<FilamentColor>('/filament-colors', {
        method: 'POST', body: JSON.stringify({ name: String(data.get('name') ?? '').trim(), color_hex: data.get('color_hex') }),
      })
      if (componentTarget !== null) {
        if (color.color_mode !== 'solid') throw new Error('Multicolor components require solid colors.')
        if (colorHexes.some((hex, index) => index !== componentTarget && hex === color.color_hex)) throw new Error('Choose a different display color for each component.')
      }
      return color
    },
    onSuccess: (color) => {
      setAdded((colors) => [...colors, color])
      if (componentTarget !== null) {
        const next = [...colorHexes]
        const names = colorHexes.map((hex, index) => colorNames[index] ?? colorOptions.find((known) => known.color_hex === hex)?.name ?? `#${hex}`)
        next[componentTarget] = color.color_hex
        names[componentTarget] = color.name
        onColorsChange(next)
        onColorNamesChange?.(names)
      } else {
        onColorNamesChange?.([])
        onNameChange(color.name)
        onModeChange(color.color_mode)
        onColorsChange(color.color_hexes)
      }
      setCreating(false)
    },
  })
  const selectRemembered = (nextName: string) => {
    onColorNamesChange?.([])
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
    // A multicolor name is reusable, but its samples belong to each product.
    if (remembered.color_mode === 'multicolor') {
      onColorsChange(colorHexes.slice(0, 3).length ? colorHexes.slice(0, 3) : ['808080'])
      return
    }
    onColorsChange(
      remembered.color_hexes?.length ? remembered.color_hexes : [remembered.color_hex],
    )
  }
  const solidOptions = colorOptions.filter((color) => color.color_mode === 'solid')
  const visibleColors = mode === 'rainbow' ? colorHexes.slice(0, 1) : colorHexes.slice(0, 3)
  const componentNames = visibleColors.map((hex, index) => colorNames[index]
    ?? solidOptions.find((color) => color.color_hex === hex)?.name ?? `#${hex}`)
  const changeCount = (count: number) => {
    const next = [...visibleColors]
    const names = [...componentNames]
    while (next.length < count) {
      const choice = solidOptions.find((color) => !next.includes(color.color_hex))
      const hex = choice?.color_hex ?? (next.length === 1 ? 'FFFFFF' : '000000')
      next.push(hex)
      names.push(choice?.name ?? '')
    }
    onColorsChange(next.slice(0, count))
    onColorNamesChange?.(count > 1 ? names.slice(0, count) : [])
    onModeChange(count > 1 ? 'multicolor' : 'solid')
    onNameChange(count > 1 ? 'Multicolor' : names[0])
  }
  const setColor = (index: number, value: string) => {
    const next = [...colorHexes]
    next[index] = value.replace('#', '').toUpperCase()
    onColorsChange(next)
  }
  const selectComponent = (index: number, value: string) => {
    const selected = solidOptions.find((color) => color.name === value)
    if (!selected) return
    const next = [...visibleColors]
    const names = [...componentNames]
    next[index] = selected.color_hex
    names[index] = selected.name
    onColorsChange(next)
    onColorNamesChange?.(names)
    onNameChange('Multicolor')
    onModeChange('multicolor')
  }
  const errorsFor = (...fields: string[]) => fields.flatMap((field) => validationErrors[field] ?? [])
  const errorBlock = (id: string, messages: string[]) => messages.length ? (
    <span className="field-validation" id={`${errorIdPrefix}-${id}-error`} role="alert">
      {messages.map((message) => <span key={message}>{message}</span>)}
    </span>
  ) : null
  const colorNameErrors = errorsFor('color_name')
  const colorModeErrors = errorsFor('color_mode', 'color_hexes', 'color_names')
  const colorSampleErrors = errorsFor('color_hex')

  return <>
    <div className="setting-field">
    <label>
      Color name
      <NewItemSelect aria-label="Color name" value={mode === 'multicolor' && visibleColors.length > 1 ? 'Multicolor' : name} required disabled={disabled || visibleColors.length > 1 && mode !== 'rainbow'} itemLabel="Color"
        onChange={(event) => selectRemembered(event.target.value)}
        onCreate={() => { setComponentTarget(null); create.reset(); setCreating(true) }}
        options={[{ value: '', label: 'Choose a color' },
          ...(mode === 'multicolor' ? [{ value: 'Multicolor', label: 'Multicolor' }] : []),
          ...colorOptions.filter((color) => color.color_mode !== 'multicolor').map((color) => ({ value: color.name, label: color.name })),
          ...(name && !(mode === 'multicolor' && name === 'Multicolor') && !colorOptions.some((color) => color.name === name) ? [{ value: name, label: name }] : [])]}
        aria-invalid={colorNameErrors.length ? true : undefined}
        aria-describedby={colorNameErrors.length ? `${errorIdPrefix}-name-error` : undefined} />
      {errorBlock('name', colorNameErrors)}
      <small className="field-help">Choose a saved color or use New Color to add a name and display color.</small>
    </label>
    {mode !== 'multicolor' ? <button className="button color-create-button" type="button" disabled={disabled} onClick={() => { setComponentTarget(null); create.reset(); setCreating(true) }}>New Color</button> : null}
    </div>
    {mode !== 'rainbow' ? <label>
      Number of colors
      <select aria-label="Number of colors" value={Math.max(1, visibleColors.length)} onChange={(event) => changeCount(Number(event.target.value))} disabled={disabled}>
        <option value="1">1 color</option><option value="2">2 colors</option><option value="3">3 colors</option>
      </select>
      <small className="field-help">Choose up to three named colors.</small>
      {errorBlock('mode', colorModeErrors)}
    </label> : null}
    {mode !== 'rainbow' ? visibleColors.map((color, index) => <label key={index}>
      {mode === 'solid' ? 'Screen color sample' : `Color ${index + 1}`}
      {mode === 'multicolor' ? <NewItemSelect itemLabel="Color" aria-label={`Color ${index + 1}`} required value={componentNames[index]} aria-invalid={colorModeErrors.length ? true : undefined} aria-describedby={colorModeErrors.length ? `${errorIdPrefix}-mode-error` : undefined} onChange={(event) => selectComponent(index, event.target.value)} disabled={disabled}
        onCreate={() => { setComponentTarget(index); create.reset(); setCreating(true) }}
        options={[
          ...(!solidOptions.some((choice) => choice.name === componentNames[index]) ? [{ value: componentNames[index], label: componentNames[index] ? `${componentNames[index]} — choose a saved color` : 'Choose a saved color' }] : []),
          ...solidOptions.map((choice) => ({ value: choice.name, label: choice.name, disabled: visibleColors.some((hex, otherIndex) => otherIndex !== index && hex === choice.color_hex) })),
        ]} /> : <input type="color" value={`#${color || '808080'}`} onChange={(event) => setColor(index, event.target.value)} disabled={disabled} aria-invalid={colorSampleErrors.length ? true : undefined} aria-describedby={colorSampleErrors.length ? `${errorIdPrefix}-sample-error` : undefined} />}
      {index === 0 ? errorBlock('sample', colorSampleErrors) : null}
    </label>) : <div className="setting-field"><span>Rainbow display</span><small className="field-help">The spool swatch uses the full rainbow spectrum.</small></div>}
    <div className="setting-field">
      <span>Preview</span>
      <span className="filament-swatch filament-swatch--large" style={filamentSwatchStyle(mode, colorHexes)} aria-label={`${name || 'Filament'} color preview`} />
      {mode === 'multicolor' ? <small className="field-help">{componentNames.join('/')}</small> : null}
    </div>
    {creating ? <Modal title="New Color" onClose={() => { if (!create.isPending) setCreating(false) }}>
      <form className="editor-form" onSubmit={(event) => { event.preventDefault(); event.stopPropagation(); create.mutate(new FormData(event.currentTarget)) }}>
        <p className="field-help">This color is saved to the list only when you save the filament.</p>
        <label>Color name<input name="name" required maxLength={96} autoFocus disabled={create.isPending} /></label>
        <label>Display color<input name="color_hex" type="color" defaultValue="#808080" disabled={create.isPending} /></label>
        {create.error ? <p className="form-error" role="alert">{create.error.message}</p> : null}
        <div className="form-actions"><button className="button" type="button" disabled={create.isPending} onClick={() => setCreating(false)}>Cancel</button><button className="button button--primary" disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Add color'}</button></div>
      </form>
    </Modal> : null}
  </>
}
