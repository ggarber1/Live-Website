import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'

import { createRecipe, getRecipe, listRecipes, removeRecipe, updateRecipe } from './api'
import RecipesPage from './RecipesPage'

vi.mock('./api')

const toast = { id: 1, title: 'Toast', ingredients: ['bread'], instructions: ['toast it'], created_at: '' }
const soup = { id: 2, title: 'Soup', ingredients: ['water', 'salt'], instructions: ['boil', 'season'], created_at: '' }

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="recipes/*" element={<RecipesPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listRecipes).mockResolvedValue([toast, soup])
  vi.mocked(getRecipe).mockImplementation(async (id) => {
    const found = [toast, soup].find((r) => r.id === id)
    if (!found) throw new Error(`no recipe with id ${id}`)
    return found
  })
  vi.mocked(createRecipe).mockResolvedValue(3)
  vi.mocked(updateRecipe).mockResolvedValue(undefined)
  vi.mocked(removeRecipe).mockResolvedValue(undefined)
})

test('the list shows a card per recipe with an ingredient count', async () => {
  renderAt('/recipes')

  expect(await screen.findByRole('link', { name: /Soup/ })).toHaveAttribute('href', '/recipes/2')
  expect(screen.getByText('2 ingredients')).toBeInTheDocument()
  expect(screen.getByText('1 ingredient')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /new recipe/i })).toHaveAttribute('href', '/recipes/new')
})

test('an empty box says so', async () => {
  vi.mocked(listRecipes).mockResolvedValue([])
  renderAt('/recipes')

  expect(await screen.findByText(/no recipes yet/i)).toBeInTheDocument()
})

test('a recipe page lists ingredients and numbers the method', async () => {
  renderAt('/recipes/2')

  expect(await screen.findByRole('heading', { name: 'Soup' })).toBeInTheDocument()
  expect(screen.getByText('2 ingredients · 2 steps')).toBeInTheDocument()
  const method = screen.getByRole('list', { name: /method/i })
  expect(method.tagName).toBe('OL')
  expect(method.querySelectorAll('li')).toHaveLength(2)
  expect(screen.getByRole('link', { name: /edit/i })).toHaveAttribute('href', '/recipes/2/edit')
})

test('an unknown recipe shows the error', async () => {
  renderAt('/recipes/9')

  expect(await screen.findByRole('alert')).toHaveTextContent('no recipe with id 9')
})

test('deleting asks first, then returns to the list', async () => {
  vi.stubGlobal('confirm', vi.fn(() => true))
  renderAt('/recipes/2')
  await screen.findByRole('heading', { name: 'Soup' })

  await userEvent.click(screen.getByRole('button', { name: /delete/i }))

  expect(await screen.findByRole('link', { name: /Toast/ })).toBeInTheDocument()
  expect(removeRecipe).toHaveBeenCalledWith(2)
  vi.unstubAllGlobals()
})

test('a new recipe is created and opened', async () => {
  renderAt('/recipes/new')

  await userEvent.type(screen.getByRole('textbox', { name: /title/i }), 'Tea')
  await userEvent.type(screen.getByRole('textbox', { name: /ingredients/i }), 'leaves')
  await userEvent.type(screen.getByRole('textbox', { name: /method/i }), 'steep')
  vi.mocked(getRecipe).mockResolvedValue({ id: 3, title: 'Tea', ingredients: ['leaves'], instructions: ['steep'], created_at: '' })
  await userEvent.click(screen.getByRole('button', { name: /save/i }))

  expect(await screen.findByRole('heading', { name: 'Tea' })).toBeInTheDocument()
  expect(createRecipe).toHaveBeenCalledWith({ title: 'Tea', ingredients: ['leaves'], instructions: ['steep'] })
})

test('editing starts from the recipe and saves back to it', async () => {
  renderAt('/recipes/2/edit')
  const title = await screen.findByRole('textbox', { name: /title/i })
  expect(title).toHaveValue('Soup')

  await userEvent.clear(title)
  await userEvent.type(title, 'Broth')
  await userEvent.click(screen.getByRole('button', { name: /save/i }))

  expect(updateRecipe).toHaveBeenCalledWith(2, {
    title: 'Broth', ingredients: ['water', 'salt'], instructions: ['boil', 'season'],
  })
})
