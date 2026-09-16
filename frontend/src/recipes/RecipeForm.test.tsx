import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import RecipeForm from './RecipeForm'

test('splits the textareas one per line, trimmed, blanks dropped', async () => {
  const onSubmit = vi.fn()
  render(<RecipeForm onSubmit={onSubmit} />)

  await userEvent.type(screen.getByRole('textbox', { name: /title/i }), 'Toast')
  await userEvent.type(screen.getByRole('textbox', { name: /ingredients/i }), ' bread \n\nbutter')
  await userEvent.type(screen.getByRole('textbox', { name: /method/i }), 'toast it\nbutter it\n')
  await userEvent.click(screen.getByRole('button', { name: /save/i }))

  expect(onSubmit).toHaveBeenCalledWith({
    title: 'Toast',
    ingredients: ['bread', 'butter'],
    instructions: ['toast it', 'butter it'],
  })
})

test('refuses a blank title', async () => {
  const onSubmit = vi.fn()
  render(<RecipeForm onSubmit={onSubmit} />)

  await userEvent.type(screen.getByRole('textbox', { name: /ingredients/i }), 'bread')
  await userEvent.click(screen.getByRole('button', { name: /save/i }))

  expect(onSubmit).not.toHaveBeenCalled()
  expect(screen.getByRole('alert')).toHaveTextContent(/title/i)
})

test('starts from an existing recipe when editing', () => {
  render(
    <RecipeForm
      initial={{ title: 'Soup', ingredients: ['water', 'salt'], instructions: ['boil'] }}
      onSubmit={() => {}}
    />,
  )

  expect(screen.getByRole('textbox', { name: /title/i })).toHaveValue('Soup')
  expect(screen.getByRole('textbox', { name: /ingredients/i })).toHaveValue('water\nsalt')
  expect(screen.getByRole('textbox', { name: /method/i })).toHaveValue('boil')
})
