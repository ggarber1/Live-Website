// The module caches the id, so each test loads a fresh copy.
async function load() {
  vi.resetModules()
  return (await import('./device')).deviceId
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

test('is stable across calls and persisted', async () => {
  const deviceId = await load()
  const first = deviceId()

  expect(first).toMatch(/^[a-z0-9-]{8,}$/)
  expect(deviceId()).toBe(first)
  expect(localStorage.getItem('livs-device-id')).toBe(first)
})

test('reads back the persisted id on a fresh load', async () => {
  const first = (await load())()

  expect((await load())()).toBe(first)
})

test('survives a browser that refuses storage', async () => {
  const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') } }
  vi.stubGlobal('localStorage', broken)
  const deviceId = await load()

  const id = deviceId()

  expect(id).toMatch(/^[a-z0-9-]{8,}$/)
  expect(deviceId()).toBe(id) // still stable within the page
})
