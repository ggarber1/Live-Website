import { useRef, useState, type ReactNode } from 'react'

import type { Track } from './api'
import Player from './Player'
import { PlayerContext } from './player-context'

// The play queue lives above the router, so leaving the music page does not
// stop the music. What plays next is decided when a row is clicked, from the
// list as it was then; searching, paging or navigating afterwards changes
// the page, not the queue.
interface Queue {
  tracks: Track[]
  index: number
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<Queue | null>(null)
  const audio = useRef<HTMLAudioElement | null>(null)
  const playing = queue ? queue.tracks[queue.index] : null

  const play = (tracks: Track[], index: number) => setQueue({ tracks, index })
  // For the cinema: a film starting should not play over the music.
  const pause = () => audio.current?.pause()
  const next = () =>
    setQueue((q) => (q && q.index + 1 < q.tracks.length ? { ...q, index: q.index + 1 } : q))

  return (
    <PlayerContext.Provider value={{ playing, play, pause }}>
      <div className={playing ? 'with-player' : undefined}>{children}</div>
      {playing && <Player track={playing} onEnded={next} audioRef={audio} />}
    </PlayerContext.Provider>
  )
}

