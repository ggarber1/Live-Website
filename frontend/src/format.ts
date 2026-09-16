import type { Track } from './api'

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
