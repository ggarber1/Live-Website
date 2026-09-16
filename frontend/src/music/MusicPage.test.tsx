import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import MusicPage from './MusicPage'
import type { Track, TrackPage } from './api'
import { listTracks } from './api'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  listTracks: vi.fn(),
}))

const mockList = vi.mocked(listTracks)

function track(id: number, title = `Track ${id}`): Track {
  return {
    id, title, artist: 'Synth', album: 'Demo', track_no: id,
    duration_seconds: 65, format: 'mp3', size_bytes: 1, created_at: '',
  }
}

function page(tracks: Track[], total = tracks.length, offset = 0): TrackPage {
  return { tracks, total, limit: 50, offset }
}

const three = [track(1), track(2), track(3)]

function player() {
  return within(screen.getByRole('contentinfo'))
}

beforeEach(() => {
  mockList.mockReset()
  mockList.mockResolvedValue(page(three))
})

test('loads the first page on mount', async () => {
  render(<MusicPage />)

  expect(await screen.findByText('Track 1')).toBeInTheDocument()
  expect(mockList).toHaveBeenCalledWith({ q: '', offset: 0 })
})

test('searching resets to the first page', async () => {
  mockList.mockResolvedValue(page(three, 120))
  render(<MusicPage />)
  await screen.findByText('Track 1')

  await userEvent.click(screen.getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(mockList).toHaveBeenCalledWith({ q: '', offset: 50 }))

  await userEvent.type(screen.getByRole('searchbox'), 'tone')
  await waitFor(() => expect(mockList).toHaveBeenCalledWith({ q: 'tone', offset: 0 }))
})

test('clicking a row plays it', async () => {
  render(<MusicPage />)
  await userEvent.click(await screen.findByText('Track 2'))

  expect(player().getByText('Track 2')).toBeInTheDocument()
  expect(document.querySelector('audio')).toHaveAttribute(
    'src', 'http://localhost:5000/api/music/tracks/2/stream',
  )
})

test('when a track ends, the next one from the list it was clicked in plays', async () => {
  render(<MusicPage />)
  await userEvent.click(await screen.findByText('Track 1'))

  // The list changes underneath the player; the queue must not.
  mockList.mockResolvedValue(page([track(9, 'Other')]))
  await userEvent.type(screen.getByRole('searchbox'), 'other')
  await screen.findByText('Other')

  fireEvent.ended(document.querySelector('audio')!)

  expect(player().getByText('Track 2')).toBeInTheDocument()
})

test('the last track ending leaves it in the player rather than looping', async () => {
  render(<MusicPage />)
  await userEvent.click(await screen.findByText('Track 3'))

  fireEvent.ended(document.querySelector('audio')!)

  expect(player().getByText('Track 3')).toBeInTheDocument()
})

test('a failed request shows the error and keeps the last good page', async () => {
  render(<MusicPage />)
  await screen.findByText('Track 1')

  mockList.mockRejectedValue(new Error('limit must be a positive integer'))
  await userEvent.type(screen.getByRole('searchbox'), 'x')

  expect(await screen.findByRole('alert')).toHaveTextContent('limit must be a positive integer')
  expect(screen.getByText('Track 1')).toBeInTheDocument()
})
