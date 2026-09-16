import { listPhotos, removePhoto, setCaption, thumbUrl, uploadPhotos } from './api'

function respond(status: number, body?: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'STATUS',
    json: () => (body === undefined ? Promise.reject(new SyntaxError()) : Promise.resolve(body)),
  })
}

afterEach(() => vi.unstubAllGlobals())

const photo = { id: 1, taken_at: 'Tue, 15 Sep 2026 09:00:00 GMT', width: 40, height: 30, format: 'jpeg', size_bytes: 1, caption: null, created_at: '' }

test('lists newest first with the envelope', async () => {
  const fetch = respond(200, { photos: [photo], total: 1, limit: 60, offset: 0 })
  vi.stubGlobal('fetch', fetch)

  const page = await listPhotos({ limit: 6 })

  expect(page.photos).toEqual([photo])
  expect(fetch.mock.calls[0][0]).toBe('http://localhost:5000/api/photos?limit=6&offset=0')
})

test('thumbnail urls come in the two sizes', () => {
  expect(thumbUrl(1)).toBe('http://localhost:5000/api/photos/1/thumb?w=400')
  expect(thumbUrl(1, 1200)).toBe('http://localhost:5000/api/photos/1/thumb?w=1200')
})

test('captions and removal', async () => {
  const fetch = respond(204)
  vi.stubGlobal('fetch', fetch)

  await setCaption(1, 'the fern')
  await removePhoto(1)

  expect(fetch.mock.calls[0][1].method).toBe('PUT')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ caption: 'the fern' })
  expect(fetch.mock.calls[1][1].method).toBe('DELETE')
})

test('upload sends every file as multipart and resolves added and rejected', async () => {
  const fetch = respond(201, { added: [photo], rejected: [{ name: 'x.txt', reason: 'not an image' }] })
  vi.stubGlobal('fetch', fetch)
  const files = [new File(['a'], 'a.jpg', { type: 'image/jpeg' }), new File(['b'], 'x.txt')]

  const result = await uploadPhotos(files)

  expect(result.added).toEqual([photo])
  expect(result.rejected[0].reason).toBe('not an image')
  const [url, init] = fetch.mock.calls[0]
  expect(url).toBe('http://localhost:5000/api/photos')
  expect(init.method).toBe('POST')
  expect(init.body).toBeInstanceOf(FormData)
  expect((init.body as FormData).getAll('files')).toHaveLength(2)
  expect(init.headers?.['Content-Type']).toBeUndefined()
})

test('an all-rejected upload still resolves with the reasons', async () => {
  vi.stubGlobal('fetch', respond(400, { added: [], rejected: [{ name: 'x.txt', reason: 'not an image' }] }))

  const result = await uploadPhotos([new File(['b'], 'x.txt')])

  expect(result.added).toEqual([])
  expect(result.rejected).toHaveLength(1)
})
