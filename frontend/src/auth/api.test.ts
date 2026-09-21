import { login, LoginError, logout } from './api'

function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300, status, statusText: 'STATUS',
    json: () => (body === undefined ? Promise.reject(new SyntaxError()) : Promise.resolve(body)),
  })
}

afterEach(() => vi.unstubAllGlobals())

test('login posts the password as JSON and resolves on 204', async () => {
  const fetch = respond(204)
  vi.stubGlobal('fetch', fetch)

  await expect(login('fern')).resolves.toBeUndefined()
  const [url, init] = fetch.mock.calls[0]
  expect(url).toBe('http://localhost:5000/api/auth/login')
  expect(JSON.parse(init.body)).toEqual({ password: 'fern' })
})

test('a wrong password rejects with the status and message', async () => {
  vi.stubGlobal('fetch', respond(401, { error: "that's not it" }))

  const err = await login('nope').catch((e) => e)
  expect(err).toBeInstanceOf(LoginError)
  expect(err.status).toBe(401)
  expect(err.message).toBe("that's not it")
})

test('logout posts', async () => {
  const fetch = respond(204)
  vi.stubGlobal('fetch', fetch)

  await logout()

  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/auth/logout')
  expect(fetch.mock.calls[0][1].method).toBe('POST')
})
