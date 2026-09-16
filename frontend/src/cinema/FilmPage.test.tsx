import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'

import { getFilm, play } from './api'
import type { Film } from './api'
import FilmPage from './FilmPage'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  getFilm: vi.fn(), play: vi.fn(),
}))
const pause = vi.fn()
vi.mock('../music/player-context', () => ({ usePlayer: () => ({ playing: null, play: () => {}, pause }) }))
vi.mock('./VideoPlayer', () => ({ default: (p: { kind: string; url: string; startAt?: number }) => <div data-testid="player">{p.kind} {p.url} from {p.startAt ?? 0}</div> }))

const soup: Film = {
  id: 'a', title: 'Paper Moon', year: 1973, runtime_seconds: 6120,
  overview: 'A con man.\n\nAnd a girl.', genres: ['Comedy', 'Drama'], has_poster: true,
  playback: 'remux', video_codec: 'h264', audio_codec: 'ac3', container: 'mkv',
  position_seconds: 0, played: false,
}

function renderAt(id = 'a') {
  return render(
    <MemoryRouter initialEntries={[`/cinema/${id}`]}>
      <Routes><Route path="cinema/:id" element={<FilmPage />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getFilm).mockResolvedValue(soup)
  vi.mocked(play).mockResolvedValue({ kind: 'hls', url: '/api/cinema/videos/x/master.m3u8', play_session_id: 's1' })
})

test('shows the film', async () => {
  renderAt()

  expect(await screen.findByRole('heading', { name: 'Paper Moon' })).toBeInTheDocument()
  expect(screen.getByText('1973 · 1h 42m')).toBeInTheDocument()
  expect(screen.getByText('Comedy · Drama')).toBeInTheDocument()
  expect(screen.getByText('A con man.')).toBeInTheDocument()
  expect(screen.getByText('And a girl.')).toBeInTheDocument()
  expect(screen.getByRole('img', { name: /Paper Moon/ })).toHaveAttribute('src', 'http://localhost:5000/api/cinema/films/a/poster?w=400')
})

test('play asks the API, then shows the player in place of the poster', async () => {
  renderAt()
  await userEvent.click(await screen.findByRole('button', { name: 'Play' }))

  expect(await screen.findByTestId('player')).toHaveTextContent('hls /api/cinema/videos/x/master.m3u8 from 0')
  expect(play).toHaveBeenCalledWith('a')
  expect(screen.queryByRole('img', { name: /Paper Moon/ })).not.toBeInTheDocument()
})

test('playing a film pauses the music', async () => {
  renderAt()
  await userEvent.click(await screen.findByRole('button', { name: 'Play' }))

  expect(pause).toHaveBeenCalledTimes(1)
})

test('a transcode film warns beside the button', async () => {
  vi.mocked(getFilm).mockResolvedValue({ ...soup, playback: 'transcode' })
  renderAt()

  expect(await screen.findByText(/will transcode/)).toBeInTheDocument()
})

test('a failed play shows the error and keeps the poster', async () => {
  vi.mocked(play).mockRejectedValue(new Error('Jellyfin is not reachable: refused'))
  renderAt()
  await userEvent.click(await screen.findByRole('button', { name: 'Play' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Jellyfin is not reachable')
  expect(screen.getByRole('img', { name: /Paper Moon/ })).toBeInTheDocument()
})

test('an unknown film shows the error', async () => {
  vi.mocked(getFilm).mockRejectedValue(new Error('no such film'))
  renderAt('zzz')

  expect(await screen.findByRole('alert')).toHaveTextContent('no such film')
})

describe('resume', () => {
  test('a film left part-way offers resume and start over', async () => {
    vi.mocked(getFilm).mockResolvedValue({ ...soup, position_seconds: 754 })
    renderAt()

    expect(await screen.findByRole('button', { name: 'Resume from 12:34' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start over' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument()
  })

  test('resume starts the player at the saved position', async () => {
    vi.mocked(getFilm).mockResolvedValue({ ...soup, position_seconds: 754 })
    renderAt()
    await userEvent.click(await screen.findByRole('button', { name: /Resume/ }))

    expect(await screen.findByTestId('player')).toHaveTextContent('from 754')
  })

  test('start over starts from the beginning', async () => {
    vi.mocked(getFilm).mockResolvedValue({ ...soup, position_seconds: 754 })
    renderAt()
    await userEvent.click(await screen.findByRole('button', { name: 'Start over' }))

    expect(await screen.findByTestId('player')).toHaveTextContent('from 0')
  })

  test('a finished film or one barely started just offers Play', async () => {
    vi.mocked(getFilm).mockResolvedValue({ ...soup, position_seconds: 754, played: true })
    renderAt()
    expect(await screen.findByRole('button', { name: 'Play' })).toBeInTheDocument()

    vi.mocked(getFilm).mockResolvedValue({ ...soup, position_seconds: 20 })
    renderAt()
    expect((await screen.findAllByRole('button', { name: 'Play' })).length).toBeGreaterThan(0)
  })
})
