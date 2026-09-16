import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import Home from './Home'
import { listPhotos } from './photos/api'

vi.mock('./photos/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./photos/api')>()),
  listPhotos: vi.fn(),
}))

function photo(id: number) {
  return { id, taken_at: 'Tue, 15 Sep 2026 09:00:00 GMT', width: 40, height: 30, format: 'jpeg', size_bytes: 1, caption: `p${id}`, created_at: '' }
}

function renderHome() {
  return render(<MemoryRouter><Home /></MemoryRouter>)
}

test('shows the newest six photos and a link to all of them', async () => {
  vi.mocked(listPhotos).mockResolvedValue({ photos: [1, 2, 3, 4, 5, 6].map(photo), total: 40, limit: 6, offset: 0 })
  renderHome()

  expect(await screen.findByText('p1')).toBeInTheDocument()
  expect(screen.getAllByRole('img')).toHaveLength(6)
  expect(screen.getByRole('link', { name: /all photos/i })).toHaveAttribute('href', '/photos')
  expect(listPhotos).toHaveBeenCalledWith({ limit: 6 })
})

test('shows no photo band at all when there are none', async () => {
  vi.mocked(listPhotos).mockResolvedValue({ photos: [], total: 0, limit: 6, offset: 0 })
  renderHome()

  await screen.findByRole('heading', { level: 1 })
  expect(screen.queryByRole('link', { name: /all photos/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})

test('a photos failure does not break the home page', async () => {
  vi.mocked(listPhotos).mockRejectedValue(new Error('PHOTOS_DIR'))
  renderHome()

  expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Recipes/ })).toBeInTheDocument()
})
