import type { FilamentColor } from '../api/types'
import { filamentSwatchStyle } from '../lib/colors'
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../api/client'
import { Modal } from './Modal'
import { NewItemSelect } from './NewItemSelect'

export type FilamentColorMode = 'solid' | 'multicolor' | 'rainbow'

export function FilamentColorEditor({
  name,
  mode,
  colorHexes,
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
  rememberedColors: FilamentColor[]
  onNameChange: (value: string) => void
  onModeChange: (value: FilamentColorMode) => void
  onColorsChange: (value: string[]) => void
  validationErrors?: Record<string, string[]>
  errorIdPrefix?: string
  disabled?: boolean
}) {
  const [creating, setCreating] = useState(false)
  const [added, setAdded] = useState<FilamentColor[]>([])
  const client = useQueryClient()
  const knownColors = [...rememberedColors, ...added.filter((color) => !rememberedColors.some((known) => known.id === color.id))]
  const colorOptions = knownColors.some((color) => color.normalized_name === 'rainbow')
    ? knownColors
    : [...knownColors, { id: 'rainbow', name: 'Rainbow', normalized_name: 'rainbow', color_hex: 'E53935', color_mode: 'rainbow' as const, color_hexes: [], record_version: 1 }]
  const create = useMutation({
    mutationFn: (data: FormData) => apiFetch<FilamentColor>('/filament-colors', {
      method: 'POST', body: JSON.stringify({ name: String(data.get('name') ?? '').trim(), color_hex: data.get('color_hex') }),
    }),
    onSuccess: async (color) => {
      setAdded((colors) => [...colors, color])
      onNameChange(color.name)
      onModeChange('solid')
      onColorsChange([color.color_hex])
      setCreating(false)
      await client.invalidateQueries({ queryKey: ['filament-colors'] })
    },
  })
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
  const errorsFor = (...fields: string[]) => fields.flatMap((field) => validationErrors[field] ?? [])
  const errorBlock = (id: string, messages: string[]) => messages.length ? (
    <span className="field-validation" id={`${errorIdPrefix}-${id}-error`} role="alert">
      {messages.map((message) => <span key={message}>{message}</span>)}
    </span>
  ) : null
  const colorNameErrors = errorsFor('color_name')
  const colorModeErrors = errorsFor('color_mode', 'color_hexes')
  const colorSampleErrors = errorsFor('color_hex')

  return <>
    <label>
      Color name
      <NewItemSelect value={name} required disabled={disabled} itemLabel="Color"
        onChange={(event) => selectRemembered(event.target.value)}
        onCreate={() => { create.reset(); setCreating(true) }}
        options={[{ value: '', label: 'Choose a color' },
          ...colorOptions.map((color) => ({ value: color.name, label: color.name })),
          ...(name && !colorOptions.some((color) => color.name === name) ? [{ value: name, label: name }] : [])]}
        aria-invalid={colorNameErrors.length ? true : undefined}
        aria-describedby={colorNameErrors.length ? `${errorIdPrefix}-name-error` : undefined} />
      {errorBlock('name', colorNameErrors)}
      <small className="field-help">Choose a saved color or use New Color to add a name and display color.</small>
    </label>
    <label>
      Display type
      <select value={mode === 'rainbow' ? 'solid' : mode} onChange={(event) => changeMode(event.target.value as FilamentColorMode)} disabled={disabled || mode === 'rainbow'} aria-invalid={colorModeErrors.length ? true : undefined} aria-describedby={colorModeErrors.length ? `${errorIdPrefix}-mode-error` : undefined}>
        <option value="solid">Solid</option>
        <option value="multicolor">Multicolor (1 to 3 colors)</option>
      </select>
      {errorBlock('mode', colorModeErrors)}
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
      <input type="color" value={`#${color || '808080'}`} onChange={(event) => setColor(index, event.target.value)} disabled={disabled} aria-invalid={colorSampleErrors.length ? true : undefined} aria-describedby={colorSampleErrors.length ? `${errorIdPrefix}-sample-error` : undefined} />
      {index === 0 ? errorBlock('sample', colorSampleErrors) : null}
    </label>) : <div className="setting-field"><span>Rainbow display</span><small className="field-help">The spool swatch uses the full rainbow spectrum.</small></div>}
    <div className="setting-field">
      <span>Preview</span>
      <span className="filament-swatch filament-swatch--large" style={filamentSwatchStyle(mode, colorHexes)} aria-label={`${name || 'Filament'} color preview`} />
    </div>
    {creating ? <Modal title="New Color" onClose={() => { if (!create.isPending) setCreating(false) }}>
      <form className="editor-form" onSubmit={(event) => { event.preventDefault(); event.stopPropagation(); create.mutate(new FormData(event.currentTarget)) }}>
        <label>Color name<input name="name" required maxLength={96} autoFocus disabled={create.isPending} /></label>
        <label>Display color<input name="color_hex" type="color" defaultValue="#808080" disabled={create.isPending} /></label>
        {create.error ? <p className="form-error" role="alert">{create.error.message}</p> : null}
        <div className="form-actions"><button className="button" type="button" disabled={create.isPending} onClick={() => setCreating(false)}>Cancel</button><button className="button button--primary" disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Add color'}</button></div>
      </form>
    </Modal> : null}
  </>
}
