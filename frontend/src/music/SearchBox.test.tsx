import { fireEvent, render, screen } from '@testing-library/react'

import SearchBox from './SearchBox'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

function type(value: string) {
  fireEvent.change(screen.getByRole('searchbox'), { target: { value } })
}

test('reports the value once, after the debounce, not per keystroke', () => {
  const onChange = vi.fn()
  render(<SearchBox onChange={onChange} />)

  type('t'); type('to'); type('ton'); type('tone')
  expect(onChange).not.toHaveBeenCalled()

  vi.advanceTimersByTime(300)
  expect(onChange).toHaveBeenCalledTimes(1)
  expect(onChange).toHaveBeenCalledWith('tone')
})

test('a cleared box reports the empty string', () => {
  const onChange = vi.fn()
  render(<SearchBox onChange={onChange} />)

  type('tone'); type('')
  vi.advanceTimersByTime(300)

  expect(onChange).toHaveBeenCalledTimes(1)
  expect(onChange).toHaveBeenCalledWith('')
})

test('shows what was typed immediately', () => {
  render(<SearchBox onChange={() => {}} />)

  type('to')

  expect(screen.getByRole('searchbox')).toHaveValue('to')
})
