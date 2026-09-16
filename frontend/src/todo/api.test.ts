import { addTodo, listTodos, removeTodo, renameTodo } from './api'

function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'STATUS',
    json: () => (body === undefined ? Promise.reject(new SyntaxError()) : Promise.resolve(body)),
  })
}

afterEach(() => vi.unstubAllGlobals())

test('lists tasks', async () => {
  const rows = [{ id: 1, task: 'milk', created_at: '' }]
  const fetch = respond(200, rows)
  vi.stubGlobal('fetch', fetch)

  expect(await listTodos()).toEqual(rows)
  expect(fetch).toHaveBeenCalledWith('http://localhost:5000/api/todo', expect.anything())
})

test('adds a task and resolves its id', async () => {
  const fetch = respond(201, { id: 7 })
  vi.stubGlobal('fetch', fetch)

  expect(await addTodo('milk')).toBe(7)

  const [url, init] = fetch.mock.calls[0]
  expect(url).toBe('http://localhost:5000/api/todo')
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body)).toEqual({ task: 'milk' })
})

test('renames a task', async () => {
  const fetch = respond(204)
  vi.stubGlobal('fetch', fetch)

  await renameTodo(7, 'oat milk')

  const [url, init] = fetch.mock.calls[0]
  expect(url).toBe('http://localhost:5000/api/todo/7')
  expect(init.method).toBe('PUT')
  expect(JSON.parse(init.body)).toEqual({ task: 'oat milk' })
})

test('removes a task', async () => {
  const fetch = respond(204)
  vi.stubGlobal('fetch', fetch)

  await removeTodo(7)

  expect(fetch.mock.calls[0][1].method).toBe('DELETE')
})

test('a 404 rejects with the API message', async () => {
  vi.stubGlobal('fetch', respond(404, { error: 'no todo with id 7' }))

  await expect(removeTodo(7)).rejects.toThrow('no todo with id 7')
})
