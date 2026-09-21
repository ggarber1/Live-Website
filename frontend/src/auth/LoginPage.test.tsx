import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'

import { login, LoginError } from './api'
import LoginPage from './LoginPage'
import { safeNext } from './next'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  login: vi.fn(),
}))

function renderAt(search = '') {
  return render(<MemoryRouter initialEntries={[`/login${search}`]}><LoginPage /></MemoryRouter>)
}

let assign: ReturnType<typeof vi.fn>
beforeEach(() => {
  vi.clearAllMocks()
  assign = vi.fn()
  vi.stubGlobal('location', { pathname: '/login', search: '', assign })
})
afterEach(() => vi.unstubAllGlobals())

test('the right password goes back where the visit was headed', async () => {
  vi.mocked(login).mockResolvedValue(undefined)
  renderAt('?next=%2Frecipes%2F3')

  await userEvent.type(screen.getByLabelText(/password/i), 'fern')
  await userEvent.click(screen.getByRole('button', { name: /come in/i }))

  expect(login).toHaveBeenCalledWith('fern')
  await waitFor(() => expect(assign).toHaveBeenCalledWith('/recipes/3'))
})

test('with nowhere to go back to, it goes home', async () => {
  vi.mocked(login).mockResolvedValue(undefined)
  renderAt()

  await userEvent.type(screen.getByLabelText(/password/i), 'fern{Enter}')

  await waitFor(() => expect(assign).toHaveBeenCalledWith('/'))
})

test('a wrong password says so and keeps the field', async () => {
  vi.mocked(login).mockRejectedValue(new LoginError(401, "that's not it"))
  renderAt()

  await userEvent.type(screen.getByLabelText(/password/i), 'nope{Enter}')

  expect(await screen.findByRole('alert')).toHaveTextContent("That's not it.")
  expect(screen.getByLabelText(/password/i)).toHaveValue('nope')
  expect(assign).not.toHaveBeenCalled()
})

test('being locked out says to wait', async () => {
  vi.mocked(login).mockRejectedValue(new LoginError(429, 'too many tries'))
  renderAt()

  await userEvent.type(screen.getByLabelText(/password/i), 'x{Enter}')

  expect(await screen.findByRole('alert')).toHaveTextContent(/half a minute/)
})

test('the button waits for a password', () => {
  renderAt()

  expect(screen.getByRole('button', { name: /come in/i })).toBeDisabled()
})

describe('safeNext', () => {
  test.each([
    [null, '/'],
    ['', '/'],
    ['/recipes/3', '/recipes/3'],
    ['https://evil.example/', '/'],
    ['//evil.example/', '/'],
    ['recipes', '/'],
  ])('%s -> %s', (raw, expected) => {
    expect(safeNext(raw)).toBe(expected)
  })
})
