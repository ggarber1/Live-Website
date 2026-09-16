import { listFilms, play, stop } from './api'

vi.mock('./device', () => ({ deviceId: () => 'dev-123' }))

function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'STATUS',
    json: () => (body === undefined ? Promise.reject(new SyntaxError()) : Promise.resolve(body)),
  })
}

afterEach(() => vi.unstubAllGlobals())

test('lists films', async () => {
  const fetch = respond(200, [{ id: 'a', title: 'Paper Moon' }])
  vi.stubGlobal('fetch', fetch)

  expect(await listFilms()).toEqual([{ id: 'a', title: 'Paper Moon' }])
  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/cinema/films')
})

test('play posts the device id and resolves the playback', async () => {
  const playback = { kind: 'hls', url: '/api/cinema/videos/x/master.m3u8?a=1', play_session_id: 's1' }
  const fetch = respond(200, playback)
  vi.stubGlobal('fetch', fetch)

  expect(await play('a')).toEqual(playback)
  const [url, init] = fetch.mock.calls[0]
  expect(url).toBe('http://localhost:5000/api/cinema/films/a/play')
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body)).toEqual({ device_id: 'dev-123' })
})

test('stop uses sendBeacon so it survives leaving the page', () => {
  const sendBeacon = vi.fn(() => true)
  vi.stubGlobal('navigator', { sendBeacon })

  stop('s1')

  const [url, blob] = sendBeacon.mock.calls[0] as unknown as [string, Blob]
  expect(url).toBe('http://localhost:5000/api/cinema/play/s1/stop')
  expect(blob.type).toBe('application/json')
})

test('stop falls back to a keepalive fetch without sendBeacon', () => {
  const fetch = respond(204)
  vi.stubGlobal('navigator', {})
  vi.stubGlobal('fetch', fetch)

  stop('s1')

  const [url, init] = fetch.mock.calls[0]
  expect(url).toBe('http://localhost:5000/api/cinema/play/s1/stop')
  expect(init.keepalive).toBe(true)
  expect(JSON.parse(init.body)).toEqual({ device_id: 'dev-123' })
})

test('a failed play rejects with the API message', async () => {
  vi.stubGlobal('fetch', respond(503, { error: 'Jellyfin is not reachable: refused' }))

  await expect(play('a')).rejects.toThrow('Jellyfin is not reachable')
})
