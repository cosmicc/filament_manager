// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useCollectionView } from '../hooks/useCollectionView'
import { CollectionViewSelector } from './CollectionViewSelector'

function Harness({ storageKey, defaultView }: { storageKey: string; defaultView: 'list' | 'cards' | 'detailed' }) {
  const [view, setView] = useCollectionView(storageKey, defaultView)
  return <><CollectionViewSelector label={storageKey} value={view} onChange={setView} /><output>{view}</output></>
}

describe('CollectionViewSelector', () => {
  afterEach(() => window.localStorage.clear())

  it('remembers each collection independently and uses its page-specific default', () => {
    const first = render(<Harness storageKey="spools" defaultView="list" />)
    expect(screen.getByText('list')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('spools view'), { target: { value: 'detailed' } })
    expect(screen.getByText('detailed')).toBeTruthy()
    first.unmount()

    const second = render(<Harness storageKey="filaments" defaultView="cards" />)
    expect(screen.getByText('cards')).toBeTruthy()
    second.unmount()

    render(<Harness storageKey="spools" defaultView="list" />)
    expect(screen.getByText('detailed')).toBeTruthy()
  })
})
