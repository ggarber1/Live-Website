import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { removePhoto, setCaption } from './api'
import Lightbox from './Lightbox'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  setCaption: vi.fn(), removePhoto: vi.fn(),
}))

const photos = [1, 2, 3].map((id) => ({
  id, taken_at: 'Tue, 15 Sep 2026 09:00:00 GMT', width: 40, height: 30, format: 'jpeg',
  size_bytes: 1, caption: id === 2 ? 'two' : null, created_at: '',
}))

function renderAt(index: number, extra: Partial<React.ComponentProps<typeof Lightbox>> = {}) {
  const props = { photos, index, onClose: vi.fn(), onIndex: vi.fn(), onCaption: vi.fn(), onRemove: vi.fn(), ...extra }
  render(<Lightbox {...props} />)
  return props
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(setCaption).mockResolvedValue(undefined)
  vi.mocked(removePhoto).mockResolvedValue(undefined)
})

test('shows the large thumbnail and the caption', () => {
  renderAt(1)

  expect(screen.getByRole('img')).toHaveAttribute('src', 'http://localhost:5000/api/photos/2/thumb?w=1200')
  expect(screen.getByText('two')).toBeInTheDocument()
})

test('arrow keys move, at the ends they do nothing', () => {
  const props = renderAt(1)

  fireEvent.keyDown(window, { key: 'ArrowRight' })
  fireEvent.keyDown(window, { key: 'ArrowLeft' })
  expect(props.onIndex).toHaveBeenNthCalledWith(1, 2)
  expect(props.onIndex).toHaveBeenNthCalledWith(2, 0)

  const last = renderAt(2)
  fireEvent.keyDown(window, { key: 'ArrowRight' })
  expect(last.onIndex).not.toHaveBeenCalled()
})

test('escape and the close button close', async () => {
  const props = renderAt(0)

  fireEvent.keyDown(window, { key: 'Escape' })
  await userEvent.click(screen.getByRole('button', { name: /close/i }))

  expect(props.onClose).toHaveBeenCalledTimes(2)
})

test('the caption is edited inline and saved', async () => {
  const props = renderAt(0)

  await userEvent.click(screen.getByRole('button', { name: /edit/i }))
  await userEvent.type(screen.getByRole('textbox'), 'the fern{Enter}')

  expect(setCaption).toHaveBeenCalledWith(1, 'the fern')
  expect(props.onCaption).toHaveBeenCalledWith(1, 'the fern')
})

test('delete asks first, then removes and reports', async () => {
  vi.stubGlobal('confirm', vi.fn(() => true))
  const props = renderAt(0)

  await userEvent.click(screen.getByRole('button', { name: /delete/i }))

  expect(removePhoto).toHaveBeenCalledWith(1)
  expect(props.onRemove).toHaveBeenCalledWith(1)
  vi.unstubAllGlobals()
})

test('a refused confirm does nothing', async () => {
  vi.stubGlobal('confirm', vi.fn(() => false))
  const props = renderAt(0)

  await userEvent.click(screen.getByRole('button', { name: /delete/i }))

  expect(removePhoto).not.toHaveBeenCalled()
  expect(props.onRemove).not.toHaveBeenCalled()
  vi.unstubAllGlobals()
})
