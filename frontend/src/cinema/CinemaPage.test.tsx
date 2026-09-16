import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'

import { listFilms } from './api'
import CinemaPage from './CinemaPage'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  listFilms: vi.fn(),
}))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="cinema/*" element={<CinemaPage />} /></Routes>
    </MemoryRouter>,
  )
}

test('the index is the grid', async () => {
  vi.mocked(listFilms).mockResolvedValue([{
    id: 'a', title: 'Paper Moon', year: 1973, runtime_seconds: 1, overview: '', genres: [],
    has_poster: true, playback: 'remux', video_codec: 'h264', audio_codec: 'ac3', container: 'mkv', position_seconds: 0, played: false,
  }])
  renderAt('/cinema')

  expect(await screen.findByRole('link', { name: /Paper Moon/ })).toHaveAttribute('href', '/cinema/a')
})

test('an empty library says so', async () => {
  vi.mocked(listFilms).mockResolvedValue([])
  renderAt('/cinema')

  expect(await screen.findByText('No films yet.')).toBeInTheDocument()
})

test('jellyfin being down is one line, not a crash', async () => {
  vi.mocked(listFilms).mockRejectedValue(new Error('Jellyfin is not reachable: refused'))
  renderAt('/cinema')

  expect(await screen.findByRole('alert')).toHaveTextContent('Jellyfin is not reachable')
})
