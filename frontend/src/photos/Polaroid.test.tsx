import { render, screen } from '@testing-library/react'

import Polaroid from './Polaroid'

const photo = { id: 7, taken_at: 'Tue, 15 Sep 2026 09:00:00 GMT', width: 40, height: 30, format: 'jpeg', size_bytes: 1, caption: null, created_at: '' }

test('shows the grid thumbnail with the caption beneath', () => {
  render(<Polaroid photo={{ ...photo, caption: 'the fern' }} />)

  expect(screen.getByRole('img')).toHaveAttribute('src', 'http://localhost:5000/api/photos/7/thumb?w=400')
  expect(screen.getByText('the fern')).toBeInTheDocument()
})

test('without a caption the date stands in, and names the image', () => {
  render(<Polaroid photo={photo} />)

  expect(screen.getByText('15 September 2026')).toBeInTheDocument()
  expect(screen.getByRole('img')).toHaveAccessibleName(/15 September 2026/)
})

test('is a button when given onOpen', () => {
  const onOpen = vi.fn()
  render(<Polaroid photo={photo} onOpen={onOpen} />)

  screen.getByRole('button').click()

  expect(onOpen).toHaveBeenCalledTimes(1)
})
