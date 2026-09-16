import { fireEvent, render, screen } from '@testing-library/react'

import type { Track } from './api'
import Player from './Player'

function track(id: number, extra: Partial<Track> = {}): Track {
  return {
    id, title: `Track ${id}`, artist: 'Synth', album: 'Demo', track_no: id,
    duration_seconds: 65, format: 'mp3', size_bytes: 1, created_at: '', ...extra,
  }
}

const play = HTMLMediaElement.prototype.play as ReturnType<typeof vi.fn>

beforeEach(() => play.mockClear())

function audio(): HTMLAudioElement {
  return document.querySelector('audio')!
}

test('with nothing to play, the audio element has no source', () => {
  render(<Player track={null} onEnded={() => {}} />)

  expect(audio()).not.toHaveAttribute('src')
  expect(play).not.toHaveBeenCalled()
})

test('given a track, it sets the stream as the source and plays', () => {
  render(<Player track={track(7)} onEnded={() => {}} />)

  expect(audio()).toHaveAttribute('src', 'http://localhost:5000/api/music/tracks/7/stream')
  expect(screen.getByText('Track 7')).toBeInTheDocument()
  expect(screen.getByText('Synth — Demo')).toBeInTheDocument()
  expect(play).toHaveBeenCalledTimes(1)
})

test('a different track changes the source and plays again', () => {
  const { rerender } = render(<Player track={track(7)} onEnded={() => {}} />)

  rerender(<Player track={track(8)} onEnded={() => {}} />)

  expect(audio()).toHaveAttribute('src', 'http://localhost:5000/api/music/tracks/8/stream')
  expect(play).toHaveBeenCalledTimes(2)
})

test('re-rendering with the same track does not restart it', () => {
  const { rerender } = render(<Player track={track(7)} onEnded={() => {}} />)

  rerender(<Player track={{ ...track(7) }} onEnded={() => {}} />)

  expect(play).toHaveBeenCalledTimes(1)
})

test('reports when the track ends', () => {
  const onEnded = vi.fn()
  render(<Player track={track(7)} onEnded={onEnded} />)

  fireEvent.ended(audio())

  expect(onEnded).toHaveBeenCalledTimes(1)
})
