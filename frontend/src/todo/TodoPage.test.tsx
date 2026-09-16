import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { addTodo, listTodos, removeTodo, renameTodo } from './api'
import TodoPage from './TodoPage'

vi.mock('./api')

const rows = [
  { id: 1, task: 'buy milk', created_at: '' },
  { id: 2, task: 'water plants', created_at: '' },
]

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listTodos).mockResolvedValue(rows)
  vi.mocked(addTodo).mockResolvedValue(3)
  vi.mocked(removeTodo).mockResolvedValue(undefined)
  vi.mocked(renameTodo).mockResolvedValue(undefined)
})

test('lists tasks oldest first', async () => {
  render(<TodoPage />)

  const items = await screen.findAllByRole('listitem')
  expect(items.map((li) => li.textContent)).toEqual([
    expect.stringContaining('buy milk'),
    expect.stringContaining('water plants'),
  ])
})

test('adding a task clears the box and shows it', async () => {
  render(<TodoPage />)
  await screen.findByText('buy milk')

  const box = screen.getByRole('textbox', { name: /new task/i })
  await userEvent.type(box, 'call mum{Enter}')

  expect(await screen.findByText('call mum')).toBeInTheDocument()
  expect(box).toHaveValue('')
  expect(addTodo).toHaveBeenCalledWith('call mum')
})

test('a blank task is not sent', async () => {
  render(<TodoPage />)
  await screen.findByText('buy milk')

  await userEvent.type(screen.getByRole('textbox', { name: /new task/i }), '   {Enter}')

  expect(addTodo).not.toHaveBeenCalled()
})

test('finishing a task removes it once the request succeeds', async () => {
  let resolve!: () => void
  vi.mocked(removeTodo).mockReturnValue(new Promise<void>((r) => { resolve = r }))
  render(<TodoPage />)
  const row = (await screen.findByText('buy milk')).closest('li')!

  await userEvent.click(within(row).getByRole('button', { name: /done/i }))
  expect(screen.getByText('buy milk')).toBeInTheDocument()

  resolve()
  await waitFor(() => expect(screen.queryByText('buy milk')).not.toBeInTheDocument())
  expect(removeTodo).toHaveBeenCalledWith(1)
})

test('a failed add shows the error and keeps the text', async () => {
  vi.mocked(addTodo).mockRejectedValue(new Error('task is required'))
  render(<TodoPage />)
  await screen.findByText('buy milk')

  await userEvent.type(screen.getByRole('textbox', { name: /new task/i }), 'x{Enter}')

  expect(await screen.findByRole('alert')).toHaveTextContent('task is required')
  expect(screen.getByRole('textbox', { name: /new task/i })).toHaveValue('x')
})

test('renaming inline saves on Enter', async () => {
  render(<TodoPage />)
  const row = (await screen.findByText('buy milk')).closest('li')!

  await userEvent.click(within(row).getByRole('button', { name: /edit/i }))
  const box = within(row).getByRole('textbox')
  await userEvent.clear(box)
  await userEvent.type(box, 'buy oat milk{Enter}')

  expect(await screen.findByText('buy oat milk')).toBeInTheDocument()
  expect(renameTodo).toHaveBeenCalledWith(1, 'buy oat milk')
})

test('renaming cancels on Escape', async () => {
  render(<TodoPage />)
  const row = (await screen.findByText('buy milk')).closest('li')!

  await userEvent.click(within(row).getByRole('button', { name: /edit/i }))
  await userEvent.type(within(row).getByRole('textbox'), 'zzz{Escape}')

  expect(screen.getByText('buy milk')).toBeInTheDocument()
  expect(renameTodo).not.toHaveBeenCalled()
})

test('says so when there is nothing to do', async () => {
  vi.mocked(listTodos).mockResolvedValue([])
  render(<TodoPage />)

  expect(await screen.findByText(/nothing to do/i)).toBeInTheDocument()
})
