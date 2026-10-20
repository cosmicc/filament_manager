// @vitest-environment jsdom
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { apiFetch } from '../api/client'
import { FilamentColorEditor, type FilamentColorMode } from './FilamentColorEditor'

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }))
afterEach(cleanup)

function Editor() {
  const [name, setName] = useState('Red')
  const [mode, setMode] = useState<FilamentColorMode>('solid')
  const [colors, setColors] = useState(['FF0000'])
  const [names, setNames] = useState<string[]>([])
  return <QueryClientProvider client={new QueryClient()}><FilamentColorEditor name={name} mode={mode} colorHexes={colors} colorNames={names} onColorNamesChange={setNames}
    onNameChange={setName} onModeChange={setMode} onColorsChange={setColors}
    rememberedColors={[
      { name: 'Red', normalized_name: 'red', color_hex: 'FF0000', color_hexes: ['FF0000'], color_mode: 'solid' },
      { name: 'White', normalized_name: 'white', color_hex: 'FFFFFF', color_hexes: ['FFFFFF'], color_mode: 'solid' },
      { name: 'Blue', normalized_name: 'blue', color_hex: '0000FF', color_hexes: ['0000FF'], color_mode: 'solid' },
      { name: 'Multicolor', normalized_name: 'multicolor', color_hex: '808080', color_hexes: [], color_mode: 'multicolor' },
    ]} /><output>{JSON.stringify({ mode, colors, names })}</output></QueryClientProvider>
}

it('forces Multicolor for two and three named samples and restores solid selection at one', () => {
  render(<Editor />)
  fireEvent.change(screen.getByLabelText('Number of colors'), { target: { value: '2' } })
  expect((screen.getByLabelText('Color name') as HTMLSelectElement).disabled).toBe(true)
  expect((screen.getByLabelText('Color name') as HTMLSelectElement).value).toBe('Multicolor')
  expect(screen.getAllByRole('option', { name: /^Multicolor$/ })).toHaveLength(1)
  fireEvent.change(screen.getByLabelText('Number of colors'), { target: { value: '3' } })
  fireEvent.change(screen.getByLabelText('Color 3'), { target: { value: 'Blue' } })
  expect(screen.getByRole('status').textContent).toContain('"names":["Red","White","Blue"]')
  fireEvent.change(screen.getByLabelText('Number of colors'), { target: { value: '1' } })
  expect((screen.getByLabelText('Color name') as HTMLSelectElement).disabled).toBe(false)
  fireEvent.change(screen.getByLabelText('Color name'), { target: { value: 'Blue' } })
  expect(screen.getByRole('status').textContent).toContain('"mode":"solid","colors":["0000FF"],"names":[]')
})

it('creates a component color without replacing the other component or leaving multicolor mode', async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce({ name: 'Black', normalized_name: 'black', color_hex: '000000', color_hexes: ['000000'], color_mode: 'solid' })
  render(<Editor />)
  fireEvent.change(screen.getByLabelText('Number of colors'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText('Color 2'), { target: { value: '__filament_manager_new_item__' } })
  const child = within(screen.getByRole('dialog', { name: 'New Color' }))
  fireEvent.change(child.getByLabelText('Color name'), { target: { value: 'Black' } })
  fireEvent.change(child.getByLabelText('Display color'), { target: { value: '#000000' } })
  fireEvent.click(child.getByRole('button', { name: 'Add color' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(screen.getByRole('status').textContent).toContain('"mode":"multicolor","colors":["FF0000","000000"],"names":["Red","Black"]')
})
