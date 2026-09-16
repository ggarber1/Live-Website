import Hls from 'hls.js'
import { useEffect, useRef, useState } from 'react'

import { BASE } from '../http'

interface Props {
  kind: 'direct' | 'hls'
  url: string
  onStop: () => void
}

const NATIVE_HLS = 'application/vnd.apple.mpegurl'

// One <video>. Direct play sets src; HLS goes through hls.js, except on
// Safari, which plays HLS itself. Leaving, by navigation or by closing the
// tab, reports a stop so Jellyfin ends the transcode.
export default function VideoPlayer({ kind, url, onStop }: Props) {
  const video = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)
  const absolute = `${BASE}${url}`

  useEffect(() => {
    const el = video.current
    if (!el) return
    let hls: Hls | null = null

    if (kind === 'direct' || el.canPlayType(NATIVE_HLS)) {
      el.src = absolute
    } else if (Hls.isSupported()) {
      hls = new Hls()
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) setError(`Playback failed: ${data.details}`)
      })
      hls.loadSource(absolute)
      hls.attachMedia(el)
    } else {
      setError('This browser cannot play streamed video.')
    }

    const stop = () => onStop()
    window.addEventListener('pagehide', stop)
    return () => {
      window.removeEventListener('pagehide', stop)
      hls?.destroy()
      stop()
    }
    // onStop is intentionally not a dependency: re-running this would restart playback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, absolute])

  return (
    <div className="video">
      <video ref={video} controls autoPlay playsInline />
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
