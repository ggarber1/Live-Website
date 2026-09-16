// The only module that knows the API's URLs.

export interface Track {
  id: number
  title: string
  artist: string | null
  album: string | null
  track_no: number | null
  duration_seconds: number | null
  format: string
  size_bytes: number
  created_at: string
}

export interface TrackPage {
  tracks: Track[]
  total: number
  limit: number
  offset: number
}

export interface ListOptions {
  q?: string
  offset?: number
}

export const PAGE_SIZE = 50

// Empty means same-origin, which is production: Flask serves the build.
// Development points it at the Flask dev server in .env.development.
const BASE = import.meta.env.VITE_API_URL ?? ''

export async function listTracks({ q = '', offset = 0 }: ListOptions): Promise<TrackPage> {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String(offset))

  const res = await fetch(`${BASE}/music/tracks?${params}`)
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}

export function streamUrl(id: number): string {
  return `${BASE}/music/tracks/${id}/stream`
}

// The API answers every error with {error}, but a proxy in front of it may
// answer with HTML, so the body is read defensively.
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (body && typeof body.error === 'string') return body.error
  } catch {
    // not JSON
  }
  return res.statusText || `request failed with status ${res.status}`
}
