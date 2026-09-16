// Jellyfin keys playback sessions by device. Each browser gets its own id so
// stopping one viewer's film cannot stop another's. Persisted when the
// browser allows it; otherwise stable for the life of the page.
const KEY = 'livs-device-id'
let inMemory: string | null = null

function fresh(): string {
  const c = globalThis.crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

export function deviceId(): string {
  if (inMemory) return inMemory
  try {
    const stored = localStorage.getItem(KEY)
    if (stored) return (inMemory = stored)
    const id = fresh()
    localStorage.setItem(KEY, id)
    return (inMemory = id)
  } catch {
    return (inMemory = fresh())
  }
}
