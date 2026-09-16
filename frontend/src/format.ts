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

// created_at arrives as an RFC 1123 string from Flask's jsonify. Rendered in
// UTC so the date does not shift with the viewer's timezone.
export function formatDate(rfc1123: string): string {
  return new Date(rfc1123).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
  })
}
