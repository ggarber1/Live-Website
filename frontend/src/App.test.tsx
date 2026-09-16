import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import App from './App'
import { listTracks } from './music/api'

vi.mock('./music/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./music/api')>()),
  listTracks: vi.fn().mockResolvedValue({ tracks: [], total: 0, limit: 50, offset: 0 }),
}))

function renderAt(path: string) {
  window.history.pushState({}, '', path)
  return render(<App />)
}

test('home greets and links to every section', () => {
  renderAt('/')

  expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  expect(screen.getByRole('main').querySelectorAll('a[href="/recipes"]').length).toBeGreaterThan(0)
})

test('a section route renders that section', () => {
  renderAt('/todo')

  expect(screen.getByRole('heading', { name: 'To-do' })).toBeInTheDocument()
})

test('the music page still lives at /music', async () => {
  renderAt('/music')

  expect(await screen.findByText('No tracks')).toBeInTheDocument()
})

test('an unknown route says so and offers the way home', () => {
  renderAt('/nowhere')

  expect(screen.getByText(/not found/i)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /home/i })).toHaveAttribute('href', '/')
})

test('music keeps playing when you leave the music page', async () => {
  const track = {
    id: 7, title: 'Track 7', artist: 'Synth', album: 'Demo', track_no: 1,
    duration_seconds: 65, format: 'mp3', size_bytes: 1, created_at: '',
  }
  vi.mocked(listTracks).mockResolvedValueOnce({ tracks: [track], total: 1, limit: 50, offset: 0 })
  renderAt('/music')
  await userEvent.click(await screen.findByText('Track 7'))
  const audio = document.querySelector('audio')!
  expect(audio).toHaveAttribute('src', 'http://localhost:5000/api/music/tracks/7/stream')

  await userEvent.click(screen.getByRole('link', { name: 'To-do' }))

  expect(await screen.findByRole('heading', { name: 'To-do' })).toBeInTheDocument()
  expect(document.querySelector('audio')).toBe(audio)
  expect(audio).toHaveAttribute('src', 'http://localhost:5000/api/music/tracks/7/stream')
  expect(screen.getByRole('contentinfo')).toHaveTextContent('Track 7')
})
