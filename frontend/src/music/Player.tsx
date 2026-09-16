import { useEffect, useRef } from 'react'

import { streamUrl, type Track } from './api'
import { describe } from './format'

interface Props {
  track: Track | null
  onEnded: () => void
}

// One <audio> element that outlives the list, so searching and paging never
// interrupt playback. Seeking is the browser's own: the stream endpoint
// answers byte-range requests.
export default function Player({ track, onEnded }: Props) {
  const audio = useRef<HTMLAudioElement>(null)
  const id = track?.id ?? null

  // Keyed on the id, not the object: the list re-renders on every keystroke
  // and hands down a fresh object each time. Only a different track restarts.
  useEffect(() => {
    if (id === null || !audio.current) return
    audio.current.play().catch(() => {
      // Autoplay refused; the controls are there for the user to press play.
    })
  }, [id])

  return (
    <footer className="player">
      <div className="now-playing">
        {track ? (
          <>
            <div className="title">{track.title}</div>
            <div className="describe">{describe(track)}</div>
          </>
        ) : (
          <div className="describe">Pick a track</div>
        )}
      </div>
      <audio ref={audio} controls src={track ? streamUrl(track.id) : undefined} onEnded={onEnded} />
    </footer>
  )
}
