import { render, screen } from '@testing-library/react'

import App from './App'

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
