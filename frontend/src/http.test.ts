import { request } from './http'

afterEach(() => vi.unstubAllGlobals())

test('a 401 sends the browser to the login page with a way back, and rejects', async () => {
  const assign = vi.fn()
  vi.stubGlobal('location', { pathname: '/recipes/3', search: '?x=1', assign })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, statusText: 'UNAUTHORIZED', json: () => Promise.resolve({ error: 'log in first' }) }))

  await expect(request('/api/recipes')).rejects.toThrow('log in first')

  expect(assign).toHaveBeenCalledWith('/login?next=%2Frecipes%2F3%3Fx%3D1')
})

test('a 401 on the login page itself does not loop', async () => {
  const assign = vi.fn()
  vi.stubGlobal('location', { pathname: '/login', search: '', assign })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, statusText: 'UNAUTHORIZED', json: () => Promise.resolve({ error: "that's not it" }) }))

  await expect(request('/api/auth/login', { method: 'POST' })).rejects.toThrow()

  expect(assign).not.toHaveBeenCalled()
})
