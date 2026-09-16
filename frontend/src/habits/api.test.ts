import { addHabit, completeHabit, listHabits, removeHabit, renameHabit } from './api'

function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'STATUS',
    json: () => (body === undefined ? Promise.reject(new SyntaxError()) : Promise.resolve(body)),
  })
}

afterEach(() => vi.unstubAllGlobals())

const habit = { id: 1, name: 'floss', streak: 2, last_completed: null, created_at: '' }

test('lists habits', async () => {
  const fetch = respond(200, [habit])
  vi.stubGlobal('fetch', fetch)

  expect(await listHabits()).toEqual([habit])
  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/habits')
})

test('adds a habit and resolves its id', async () => {
  const fetch = respond(201, { id: 4 })
  vi.stubGlobal('fetch', fetch)

  expect(await addHabit('floss')).toBe(4)
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ name: 'floss' })
})

test('renames and removes', async () => {
  const fetch = respond(204)
  vi.stubGlobal('fetch', fetch)

  await renameHabit(4, 'floss nightly')
  await removeHabit(4)

  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/habits/4')
  expect(fetch.mock.calls[0][1].method).toBe('PUT')
  expect(fetch.mock.calls[1][1].method).toBe('DELETE')
})

test('completing resolves the updated habit', async () => {
  const updated = { ...habit, streak: 3, last_completed: 'Wed, 16 Sep 2026 00:00:00 GMT' }
  const fetch = respond(200, updated)
  vi.stubGlobal('fetch', fetch)

  expect(await completeHabit(1)).toEqual(updated)
  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/habits/1/complete')
  expect(fetch.mock.calls[0][1].method).toBe('POST')
})

test('a 404 rejects with the API message', async () => {
  vi.stubGlobal('fetch', respond(404, { error: 'no habit with id 9' }))

  await expect(completeHabit(9)).rejects.toThrow('no habit with id 9')
})
