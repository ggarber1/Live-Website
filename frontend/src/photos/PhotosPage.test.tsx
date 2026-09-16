import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { listPhotos, uploadPhotos } from './api'
import PhotosPage from './PhotosPage'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  listPhotos: vi.fn(), uploadPhotos: vi.fn(), setCaption: vi.fn(), removePhoto: vi.fn(),
}))

function photo(id: number, caption: string | null = null) {
  return { id, taken_at: 'Tue, 15 Sep 2026 09:00:00 GMT', width: 40, height: 30, format: 'jpeg', size_bytes: 1, caption, created_at: '' }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listPhotos).mockResolvedValue({ photos: [photo(1, 'one'), photo(2, 'two')], total: 2, limit: 60, offset: 0 })
})

test('shows the photos as polaroids', async () => {
  render(<PhotosPage />)

  expect(await screen.findByText('one')).toBeInTheDocument()
  expect(screen.getAllByRole('img')).toHaveLength(2)
})

test('an empty library says so', async () => {
  vi.mocked(listPhotos).mockResolvedValue({ photos: [], total: 0, limit: 60, offset: 0 })
  render(<PhotosPage />)

  expect(await screen.findByText('No photos yet.')).toBeInTheDocument()
})

test('uploading prepends what was added and shows why the rest was refused', async () => {
  vi.mocked(uploadPhotos).mockResolvedValue({ added: [photo(3, 'three')], rejected: [{ name: 'x.txt', reason: 'not an image' }] })
  render(<PhotosPage />)
  await screen.findByText('one')

  const input = screen.getByLabelText(/add photos/i) as HTMLInputElement
  await userEvent.upload(input, [new File(['a'], 'a.jpg', { type: 'image/jpeg' }), new File(['b'], 'x.txt')])

  expect(uploadPhotos).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(screen.getAllByRole('img')).toHaveLength(3))
  const captions = screen.getAllByText(/^(one|two|three)$/).map((e) => e.textContent)
  expect(captions).toEqual(['three', 'one', 'two'])
  expect(screen.getByRole('alert')).toHaveTextContent('x.txt: not an image')
})

test('opening a polaroid shows the lightbox', async () => {
  render(<PhotosPage />)
  await screen.findByText('one')

  await userEvent.click(screen.getAllByRole('button', { name: /one/ })[0])

  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByRole('dialog').querySelector('img')).toHaveAttribute('src', expect.stringContaining('w=1200'))
})

test('a failed listing is one line', async () => {
  vi.mocked(listPhotos).mockRejectedValue(new Error('missing environment variable: PHOTOS_DIR'))
  render(<PhotosPage />)

  expect(await screen.findByRole('alert')).toHaveTextContent('PHOTOS_DIR')
})
