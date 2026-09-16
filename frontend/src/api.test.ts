import { listTracks, streamUrl } from './api'

const page = { tracks: [], total: 0, limit: 50, offset: 0 }

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 400 ? 'BAD REQUEST' : 'OK',
    json: () => Promise.resolve(body),
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('listTracks', () => {
  test('requests the page with the search term and offset', async () => {
    const fetch = respond(200, page)
    vi.stubGlobal('fetch', fetch)

    const result = await listTracks({ q: 'tone', offset: 50 })

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:5000/music/tracks?q=tone&limit=50&offset=50',
    )
    expect(result).toEqual(page)
  })

  test('omits an empty search term from the query string', async () => {
    const fetch = respond(200, page)
    vi.stubGlobal('fetch', fetch)

    await listTracks({})

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:5000/music/tracks?limit=50&offset=0',
    )
  })

  test('surfaces the error body of a failed request', async () => {
    vi.stubGlobal('fetch', respond(400, { error: 'limit must be a positive integer' }))

    await expect(listTracks({})).rejects.toThrow('limit must be a positive integer')
  })

  test('falls back to the status text when the error body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      statusText: 'BAD GATEWAY',
      json: () => Promise.reject(new SyntaxError('not json')),
    }))

    await expect(listTracks({})).rejects.toThrow('BAD GATEWAY')
  })
})

test('streamUrl points at the track stream', () => {
  expect(streamUrl(7)).toBe('http://localhost:5000/music/tracks/7/stream')
})
