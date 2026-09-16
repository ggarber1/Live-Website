import { BASE, json, request } from '../http'

export interface Photo {
  id: number
  taken_at: string
  width: number
  height: number
  format: string
  size_bytes: number
  caption: string | null
  created_at: string
}

export interface PhotoPage {
  photos: Photo[]
  total: number
  limit: number
  offset: number
}

export interface UploadResult {
  added: Photo[]
  rejected: { name: string; reason: string }[]
}

export type ThumbWidth = 400 | 1200

export function listPhotos({ limit = 60, offset = 0 }: { limit?: number; offset?: number } = {}): Promise<PhotoPage> {
  return request(`/api/photos?limit=${limit}&offset=${offset}`)
}

export function thumbUrl(id: number, width: ThumbWidth = 400): string {
  return `${BASE}/api/photos/${id}/thumb?w=${width}`
}

export function setCaption(id: number, caption: string): Promise<void> {
  return request(`/api/photos/${id}`, { method: 'PUT', ...json({ caption }) })
}

export function removePhoto(id: number): Promise<void> {
  return request(`/api/photos/${id}`, { method: 'DELETE' })
}

// Multipart, so not through request(): the browser sets the boundary
// header itself, and a 400 here still carries the per-file reasons.
export async function uploadPhotos(files: File[]): Promise<UploadResult> {
  const body = new FormData()
  for (const file of files) body.append('files', file, file.name)
  const res = await fetch(`${BASE}/api/photos`, { method: 'POST', body })
  let parsed: unknown = null
  try {
    parsed = await res.json()
  } catch {
    // not JSON
  }
  if (parsed && typeof parsed === 'object' && 'added' in parsed && 'rejected' in parsed) {
    return parsed as UploadResult
  }
  const error = parsed && typeof parsed === 'object' && 'error' in parsed ? String((parsed as { error: unknown }).error) : res.statusText
  throw new Error(error || `upload failed with status ${res.status}`)
}
