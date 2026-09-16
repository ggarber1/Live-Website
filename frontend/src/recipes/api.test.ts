import { createRecipe, getRecipe, listRecipes, removeRecipe, updateRecipe } from './api'

function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'STATUS',
    json: () => (body === undefined ? Promise.reject(new SyntaxError()) : Promise.resolve(body)),
  })
}

afterEach(() => vi.unstubAllGlobals())

const toast = { id: 1, title: 'Toast', ingredients: ['bread'], instructions: ['toast it'], created_at: '' }
const soup = { id: 2, title: 'Soup', ingredients: ['water', 'salt'], instructions: ['boil'], created_at: '' }

test('lists recipes', async () => {
  const fetch = respond(200, [toast, soup])
  vi.stubGlobal('fetch', fetch)

  expect(await listRecipes()).toEqual([toast, soup])
  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/recipes')
})

test('getRecipe finds one in the list, since there is no single-recipe endpoint', async () => {
  vi.stubGlobal('fetch', respond(200, [toast, soup]))

  expect(await getRecipe(2)).toEqual(soup)
})

test('getRecipe rejects for an unknown id', async () => {
  vi.stubGlobal('fetch', respond(200, [toast]))

  await expect(getRecipe(9)).rejects.toThrow('no recipe with id 9')
})

test('creates and resolves the id', async () => {
  const fetch = respond(201, { id: 3 })
  vi.stubGlobal('fetch', fetch)

  const draft = { title: 'Tea', ingredients: ['leaves'], instructions: ['steep'] }
  expect(await createRecipe(draft)).toBe(3)
  expect(fetch.mock.calls[0][1].method).toBe('POST')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(draft)
})

test('updates and removes', async () => {
  const fetch = respond(204)
  vi.stubGlobal('fetch', fetch)

  await updateRecipe(3, { title: 'Tea', ingredients: [], instructions: [] })
  await removeRecipe(3)

  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/recipes/3')
  expect(fetch.mock.calls[0][1].method).toBe('PUT')
  expect(fetch.mock.calls[1][1].method).toBe('DELETE')
})

test('a 400 rejects with the API message', async () => {
  vi.stubGlobal('fetch', respond(400, { error: 'ingredients must be an array of strings' }))

  await expect(createRecipe({ title: 'x', ingredients: [], instructions: [] }))
    .rejects.toThrow('ingredients must be an array of strings')
})
