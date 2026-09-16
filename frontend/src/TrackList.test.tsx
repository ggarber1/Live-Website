import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import type { Track } from './api'
import TrackList from './TrackList'

function track(id: number, extra: Partial<Track> = {}): Track {
  return {
    id, title: `Track ${id}`, artist: 'Synth', album: 'Demo', track_no: id,
    duration_seconds: 65, format: 'mp3', size_bytes: 1, created_at: '', ...extra,
  }
}

const noop = () => {}

function renderList(props: Partial<React.ComponentProps<typeof TrackList>> = {}) {
  const defaults = {
    tracks: [track(1), track(2)], total: 2, offset: 0, limit: 50,
    playingId: null, onPlay: noop, onPage: noop,
  }
  return render(<TrackList {...defaults} {...props} />)
}

test('renders a row per track with title, description and duration', () => {
  renderList()

  const rows = screen.getAllByRole('row').slice(1) // skip the header
  expect(rows).toHaveLength(2)
  expect(within(rows[0]).getByText('Track 1')).toBeInTheDocument()
  expect(within(rows[0]).getByText('Synth — Demo')).toBeInTheDocument()
  expect(within(rows[0]).getByText('1:05')).toBeInTheDocument()
})

test('an untagged track shows its title and nothing else, never "null"', () => {
  renderList({
    tracks: [track(1, { artist: null, album: null, duration_seconds: null })],
    total: 1,
  })

  expect(screen.getByText('Track 1')).toBeInTheDocument()
  expect(screen.queryByText(/null/)).not.toBeInTheDocument()
})

test('clicking a row plays that track', async () => {
  const onPlay = vi.fn()
  renderList({ onPlay })

  await userEvent.click(screen.getByText('Track 2'))

  expect(onPlay).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))
})

test('the playing row is marked current', () => {
  renderList({ playingId: 2 })

  const rows = screen.getAllByRole('row').slice(1)
  expect(rows[0]).not.toHaveAttribute('aria-current')
  expect(rows[1]).toHaveAttribute('aria-current', 'true')
})

describe('pager', () => {
  test('first page: range, Next enabled, Previous disabled', () => {
    renderList({ total: 120 })

    expect(screen.getByText('1–50 of 120')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  })

  test('last page: range clipped to total, Next disabled', () => {
    renderList({ total: 120, offset: 100 })

    expect(screen.getByText('101–120 of 120')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled()
  })

  test('Next and Previous report the new offset', async () => {
    const onPage = vi.fn()
    renderList({ total: 120, offset: 50, onPage })

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }))

    expect(onPage).toHaveBeenNthCalledWith(1, 100)
    expect(onPage).toHaveBeenNthCalledWith(2, 0)
  })

  test('an empty library says so and has no pager', () => {
    renderList({ tracks: [], total: 0 })

    expect(screen.getByText('No tracks')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
  })
})
