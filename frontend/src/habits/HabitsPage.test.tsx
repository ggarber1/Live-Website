import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { addHabit, completeHabit, listHabits, removeHabit, renameHabit } from './api'
import HabitsPage from './HabitsPage'

vi.mock('./api')

const now = new Date()
const TODAY = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())).toUTCString()

const rows = [
  { id: 1, name: 'floss', streak: 3, last_completed: 'Mon, 01 Jan 2024 00:00:00 GMT', created_at: '' },
  { id: 2, name: 'stretch', streak: 1, last_completed: TODAY, created_at: '' },
  { id: 3, name: 'read', streak: 0, last_completed: null, created_at: '' },
]

function row(name: string) {
  return screen.getByText(name).closest('li')!
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listHabits).mockResolvedValue(rows)
  vi.mocked(addHabit).mockResolvedValue(9)
  vi.mocked(removeHabit).mockResolvedValue(undefined)
  vi.mocked(renameHabit).mockResolvedValue(undefined)
})

test('shows each habit with its streak', async () => {
  render(<HabitsPage />)
  await screen.findByText('floss')

  expect(within(row('floss')).getByText('3 days')).toBeInTheDocument()
  expect(within(row('stretch')).getByText('1 day')).toBeInTheDocument()
  expect(within(row('read')).getByText('no streak yet')).toBeInTheDocument()
})

test('a habit done today is marked and cannot be done again', async () => {
  render(<HabitsPage />)
  await screen.findByText('stretch')

  const done = within(row('stretch')).getByRole('button', { name: /done/i })
  expect(done).toBeDisabled()
  expect(done).toHaveTextContent(/done/i)
  expect(within(row('floss')).getByRole('button', { name: /done today/i })).toBeEnabled()
})

test('completing a habit takes the streak from the response', async () => {
  vi.mocked(completeHabit).mockResolvedValue({ ...rows[0], streak: 4, last_completed: TODAY })
  render(<HabitsPage />)
  await screen.findByText('floss')

  await userEvent.click(within(row('floss')).getByRole('button', { name: /done today/i }))

  expect(await within(row('floss')).findByText('4 days')).toBeInTheDocument()
  expect(within(row('floss')).getByRole('button', { name: /done/i })).toBeDisabled()
  expect(completeHabit).toHaveBeenCalledWith(1)
})

test('adds a habit', async () => {
  render(<HabitsPage />)
  await screen.findByText('floss')

  await userEvent.type(screen.getByRole('textbox', { name: /new habit/i }), 'journal{Enter}')

  expect(await screen.findByText('journal')).toBeInTheDocument()
  expect(addHabit).toHaveBeenCalledWith('journal')
})

test('removes a habit after confirming', async () => {
  vi.stubGlobal('confirm', vi.fn(() => true))
  render(<HabitsPage />)
  await screen.findByText('read')

  await userEvent.click(within(row('read')).getByRole('button', { name: /remove/i }))

  expect(await screen.findByText('floss')).toBeInTheDocument()
  expect(screen.queryByText('read')).not.toBeInTheDocument()
  expect(removeHabit).toHaveBeenCalledWith(3)
  vi.unstubAllGlobals()
})

test('renames inline', async () => {
  render(<HabitsPage />)
  await screen.findByText('floss')

  const floss = row('floss')
  await userEvent.click(within(floss).getByRole('button', { name: /edit/i }))
  const box = within(floss).getByRole('textbox')
  await userEvent.clear(box)
  await userEvent.type(box, 'floss nightly{Enter}')

  expect(await screen.findByText('floss nightly')).toBeInTheDocument()
  expect(renameHabit).toHaveBeenCalledWith(1, 'floss nightly')
})

test('a failed completion shows the error', async () => {
  vi.mocked(completeHabit).mockRejectedValue(new Error('no habit with id 1'))
  render(<HabitsPage />)
  await screen.findByText('floss')

  await userEvent.click(within(row('floss')).getByRole('button', { name: /done today/i }))

  expect(await screen.findByRole('alert')).toHaveTextContent('no habit with id 1')
})

test('says so when there are no habits', async () => {
  vi.mocked(listHabits).mockResolvedValue([])
  render(<HabitsPage />)

  expect(await screen.findByText(/no habits yet/i)).toBeInTheDocument()
})
