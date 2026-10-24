import type { Track } from './music/api'

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m)
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

// The artist/album line under a title. Untagged tracks have neither.
export function describe(track: Track): string {
  return [track.artist, track.album].filter(Boolean).join(' — ')
}

// Dates arrive as RFC 1123 strings from Flask's jsonify, always labelled GMT.

// For wall-clock times with no zone, like a photo's EXIF taken_at: rendered in
// UTC, which is how they were labelled, so the day never shifts.
export function formatDate(rfc1123: string): string {
  return new Date(rfc1123).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
  })
}

// For real moments, like when a post was written: the API sends true UTC, so
// this shows the day it was where the viewer is.
export function formatLocalDate(rfc1123: string, timeZone?: string): string {
  return new Date(rfc1123).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone,
  })
}

// Film runtimes read as "1h 42m"; under an hour, "48m".
export function formatRuntime(seconds: number | null): string {
  if (seconds === null) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}
