import Hls from 'hls.js'
import { useEffect, useMemo, useRef, useState } from 'react'

import { BASE } from '../http'

interface Props {
  kind: 'direct' | 'hls'
  url: string
  onStop: () => void
  startAt?: number
  onProgress?: (seconds: number, finished: boolean) => void
}

const PROGRESS_EVERY_MS = 30_000

const NATIVE_HLS = 'application/vnd.apple.mpegurl'

// One <video>. Direct play sets src; HLS goes through hls.js, except on
// Safari, which plays HLS itself. Leaving, by navigation or by closing the
// tab, reports a stop so Jellyfin ends the transcode, and reports where the
// film was left. Progress also goes out on pause and every half minute, so a
// crash loses at most that much.
export default function VideoPlayer({ kind, url, onStop, startAt = 0, onProgress }: Props) {
  const video = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)
  const absolute = `${BASE}${url}`
  // Callbacks are read through a ref so changing them never restarts playback.
  const latest = useRef({ onStop, onProgress, startAt })
  useEffect(() => {
    latest.current = { onStop, onProgress, startAt }
  })
  // Decided once, in render, so "cannot play" is derived rather than set from the effect.
  const nativeHls = useMemo(() => document.createElement('video').canPlayType(NATIVE_HLS) !== '', [])
  const unsupported = kind === 'hls' && !nativeHls && !Hls.isSupported()

  useEffect(() => {
    const el = video.current
    if (!el) return
    let hls: Hls | null = null

    if (kind === 'direct' || nativeHls) {
      el.src = absolute
    } else if (Hls.isSupported()) {
      hls = new Hls()
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) setError(`Playback failed: ${data.details}`)
      })
      hls.loadSource(absolute)
      hls.attachMedia(el)
    }

    let finished = false
    let lastReport = 0
    const report = (force = false) => {
      if (finished) return
      if (!force && Date.now() - lastReport < PROGRESS_EVERY_MS) return
      lastReport = Date.now()
      latest.current.onProgress?.(el.currentTime, false)
    }
    const onLoaded = () => {
      if (latest.current.startAt > 0) el.currentTime = latest.current.startAt
    }
    const onPause = () => report(true)
    const onTime = () => report()
    const onEnded = () => {
      finished = true
      latest.current.onProgress?.(0, true)
    }
    el.addEventListener('loadedmetadata', onLoaded)
    el.addEventListener('pause', onPause)
    el.addEventListener('timeupdate', onTime)
    el.addEventListener('ended', onEnded)

    const leave = () => {
      report(true)
      latest.current.onStop()
    }
    window.addEventListener('pagehide', leave)
    return () => {
      window.removeEventListener('pagehide', leave)
      el.removeEventListener('loadedmetadata', onLoaded)
      el.removeEventListener('pause', onPause)
      el.removeEventListener('timeupdate', onTime)
      el.removeEventListener('ended', onEnded)
      hls?.destroy()
      leave()
    }
  }, [kind, absolute, nativeHls])

  return (
    <div className="video">
      <video ref={video} controls autoPlay playsInline />
      {(error || unsupported) && <p role="alert">{error ?? 'This browser cannot play streamed video.'}</p>}
    </div>
  )
}
