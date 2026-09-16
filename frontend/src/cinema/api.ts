import { BASE, json, request } from '../http'
import { deviceId } from './device'

export type PlaybackKind = 'direct' | 'remux' | 'transcode' | 'unknown'

export interface Film {
  id: string
  title: string
  year: number | null
  runtime_seconds: number | null
  overview: string
  genres: string[]
  has_poster: boolean
  playback: PlaybackKind
  video_codec: string | null
  audio_codec: string | null
  container: string | null
}

export interface Playback {
  kind: 'direct' | 'hls'
  url: string
  play_session_id: string
}

export function listFilms(): Promise<Film[]> {
  return request('/api/cinema/films')
}

export function getFilm(id: string): Promise<Film> {
  return request(`/api/cinema/films/${id}`)
}

export function play(id: string): Promise<Playback> {
  return request(`/api/cinema/films/${id}/play`, { method: 'POST', ...json({ device_id: deviceId() }) })
}

export function posterUrl(id: string, width = 300): string {
  return `${BASE}/api/cinema/films/${id}/poster?w=${width}`
}

// Fired on unmount and on pagehide, so it must survive the page going away.
// sendBeacon is built for exactly that; keepalive fetch is the fallback.
export function stop(playSessionId: string): void {
  const url = `${BASE}/api/cinema/play/${playSessionId}/stop`
  const body = JSON.stringify({ device_id: deviceId() })
  if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }))
    return
  }
  fetch(url, { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' }, body })
    .catch(() => {})
}
