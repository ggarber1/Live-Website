import { createPost, getPost, listPosts, removePost, updatePost } from './api'

function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'STATUS',
    json: () => (body === undefined ? Promise.reject(new SyntaxError()) : Promise.resolve(body)),
  })
}

afterEach(() => vi.unstubAllGlobals())

const post = { id: 1, title: 'Rain', content: 'It rained.', created_at: 'Tue, 15 Sep 2026 20:00:00 GMT' }

test('the journal reads and writes the blog endpoints', async () => {
  const fetch = respond(200, [post])
  vi.stubGlobal('fetch', fetch)

  expect(await listPosts()).toEqual([post])
  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/blog')
})

test('getPost finds one in the list and rejects for an unknown id', async () => {
  vi.stubGlobal('fetch', respond(200, [post]))

  expect(await getPost(1)).toEqual(post)
  await expect(getPost(2)).rejects.toThrow('no entry with id 2')
})

test('creates, updates and removes', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 201, json: () => Promise.resolve({ id: 5 }) })
    .mockResolvedValue({ ok: true, status: 204, json: () => Promise.reject(new SyntaxError()) })
  vi.stubGlobal('fetch', fetch)

  expect(await createPost({ title: 'Rain', content: 'It rained.' })).toBe(5)
  await updatePost(5, { title: 'Rain', content: 'It poured.' })
  await removePost(5)

  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/blog')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ title: 'Rain', content: 'It rained.' })
  expect(fetch.mock.calls[1][0]).toBe('http://localhost:5000/api/blog/5')
  expect(fetch.mock.calls[1][1].method).toBe('PUT')
  expect(fetch.mock.calls[2][1].method).toBe('DELETE')
})
