import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'

import { createPost, getPost, listPosts, removePost, updatePost } from './api'
import BlogPage from './BlogPage'

vi.mock('./api')

const long = 'A'.repeat(200)
const rain = { id: 2, title: 'Rain', content: 'It rained.\n\nThen it stopped.', created_at: 'Wed, 16 Sep 2026 08:00:00 GMT' }
const sun = { id: 1, title: 'Sun', content: long, created_at: 'Tue, 15 Sep 2026 08:00:00 GMT' }

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="blog/*" element={<BlogPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listPosts).mockResolvedValue([rain, sun])
  vi.mocked(getPost).mockImplementation(async (id) => {
    const found = [rain, sun].find((p) => p.id === id)
    if (!found) throw new Error(`no post with id ${id}`)
    return found
  })
  vi.mocked(createPost).mockResolvedValue(3)
  vi.mocked(updatePost).mockResolvedValue(undefined)
  vi.mocked(removePost).mockResolvedValue(undefined)
})

test('entries are listed as given, with date and a short excerpt', async () => {
  renderAt('/blog')

  const links = await screen.findAllByRole('link', { name: /Rain|Sun/ })
  expect(links.map((a) => a.getAttribute('href'))).toEqual(['/blog/2', '/blog/1'])
  expect(screen.getByText('16 September 2026')).toBeInTheDocument()
  expect(screen.getByText('A'.repeat(160) + '…')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /write/i })).toHaveAttribute('href', '/blog/new')
})

test('an empty blog says so', async () => {
  vi.mocked(listPosts).mockResolvedValue([])
  renderAt('/blog')

  expect(await screen.findByText(/nothing written yet/i)).toBeInTheDocument()
})

test('an entry splits paragraphs on blank lines', async () => {
  renderAt('/blog/2')

  expect(await screen.findByRole('heading', { name: 'Rain' })).toBeInTheDocument()
  expect(screen.getByText('16 September 2026')).toBeInTheDocument()
  const paragraphs = screen.getByRole('article').querySelectorAll('p')
  expect(Array.from(paragraphs).map((p) => p.textContent)).toEqual(['It rained.', 'Then it stopped.'])
  expect(screen.getByRole('link', { name: /edit/i })).toHaveAttribute('href', '/blog/2/edit')
})

test('writing requires a title and content', async () => {
  renderAt('/blog/new')

  await userEvent.click(await screen.findByRole('button', { name: /save/i }))

  expect(screen.getByRole('alert')).toBeInTheDocument()
  expect(createPost).not.toHaveBeenCalled()
})

test('a new entry is saved and opened', async () => {
  renderAt('/blog/new')

  await userEvent.type(screen.getByRole('textbox', { name: /title/i }), 'Tea')
  await userEvent.type(screen.getByRole('textbox', { name: /post/i }), 'Had some.')
  vi.mocked(getPost).mockResolvedValue({ id: 3, title: 'Tea', content: 'Had some.', created_at: 'Wed, 16 Sep 2026 09:00:00 GMT' })
  await userEvent.click(screen.getByRole('button', { name: /save/i }))

  expect(await screen.findByRole('heading', { name: 'Tea' })).toBeInTheDocument()
  expect(createPost).toHaveBeenCalledWith({ title: 'Tea', content: 'Had some.' })
})

test('editing saves back to the entry', async () => {
  renderAt('/blog/2/edit')
  const title = await screen.findByRole('textbox', { name: /title/i })
  expect(title).toHaveValue('Rain')

  await userEvent.clear(title)
  await userEvent.type(title, 'Drizzle')
  await userEvent.click(screen.getByRole('button', { name: /save/i }))

  expect(updatePost).toHaveBeenCalledWith(2, { title: 'Drizzle', content: rain.content })
})

test('deleting asks first, then returns to the journal', async () => {
  vi.stubGlobal('confirm', vi.fn(() => true))
  renderAt('/blog/2')
  await screen.findByRole('heading', { name: 'Rain' })

  await userEvent.click(screen.getByRole('button', { name: /delete/i }))

  expect(await screen.findByRole('link', { name: /Sun/ })).toBeInTheDocument()
  expect(removePost).toHaveBeenCalledWith(2)
  vi.unstubAllGlobals()
})
