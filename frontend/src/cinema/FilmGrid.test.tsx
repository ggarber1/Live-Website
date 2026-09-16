import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import type { Film } from './api'
import FilmGrid from './FilmGrid'

function film(id: string, extra: Partial<Film> = {}): Film {
  return {
    id, title: `Film ${id}`, year: 1973, runtime_seconds: 6120, overview: 'x', genres: [],
    has_poster: true, playback: 'remux', video_codec: 'h264', audio_codec: 'ac3', container: 'mkv', ...extra,
  }
}

function renderGrid(films: Film[]) {
  return render(<MemoryRouter><FilmGrid films={films} /></MemoryRouter>)
}

test('a card per film with poster, title and year, linking to the film', () => {
  renderGrid([film('a'), film('b', { year: 1951 })])

  const card = screen.getByRole('link', { name: /Film a/ })
  expect(card).toHaveAttribute('href', '/cinema/a')
  expect(within(card).getByRole('img')).toHaveAttribute('src', 'http://localhost:5000/api/cinema/films/a/poster?w=300')
  expect(within(card).getByText('1973')).toBeInTheDocument()
  expect(screen.getByText('1951')).toBeInTheDocument()
})

test('a film that will transcode says so', () => {
  renderGrid([film('a', { playback: 'transcode' }), film('b')])

  expect(within(screen.getByRole('link', { name: /Film a/ })).getByText('will transcode')).toBeInTheDocument()
  expect(within(screen.getByRole('link', { name: /Film b/ })).queryByText('will transcode')).not.toBeInTheDocument()
})

test('no poster gives a paper placeholder rather than a broken image', () => {
  renderGrid([film('a', { has_poster: false })])

  const card = screen.getByRole('link', { name: /Film a/ })
  expect(within(card).queryByRole('img')).not.toBeInTheDocument()
  expect(within(card).getByText('Film a')).toBeInTheDocument()
})
