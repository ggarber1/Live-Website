// Shared request helper: base URL, JSON encoding, and error surfacing.
// Every service's api.ts goes through here so an API error message reaches
// the page instead of rendering as an empty list.

export const BASE = import.meta.env.VITE_API_URL ?? ''

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: typeof init.body === 'string' ? { 'Content-Type': 'application/json', ...init.headers } : init.headers,
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  if (res.status === 204) return undefined as T
  return res.json()
}

export function json(body: unknown): RequestInit {
  return { body: JSON.stringify(body) }
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
