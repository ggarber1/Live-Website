import { useCallback, useEffect, useState } from 'react'

import { listTracks, PAGE_SIZE, type Track, type TrackPage } from './api'
import Player from './Player'
import SearchBox from './SearchBox'
import TrackList from './TrackList'

// What plays next is decided when a row is clicked, from the list as it was
// then. Searching or paging afterwards changes the list, not the queue.
interface Queue {
  tracks: Track[]
  index: number
}

export default function MusicPage() {
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<TrackPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [queue, setQueue] = useState<Queue | null>(null)

  useEffect(() => {
    let stale = false
    listTracks({ q: query, offset }).then(
      (result) => {
        if (stale) return
        setPage(result)
        setError(null)
      },
      (err: Error) => {
        if (!stale) setError(err.message)
      },
    )
    // A slow response for an old query must not overwrite a newer page.
    return () => {
      stale = true
    }
  }, [query, offset])

  // Stable, so the search box's debounce timer is not reset by re-renders.
  const search = useCallback((q: string) => {
    setQuery(q)
    setOffset(0)
  }, [])

  const play = (track: Track) => {
    if (!page) return
    setQueue({ tracks: page.tracks, index: page.tracks.findIndex((t) => t.id === track.id) })
  }

  const next = () => {
    setQueue((q) => (q && q.index + 1 < q.tracks.length ? { ...q, index: q.index + 1 } : q))
  }

  const playing = queue ? queue.tracks[queue.index] : null

  return (
    <>
      <div className="music">
        <h1>Music</h1>
        <SearchBox onChange={search} />
        {error && <p role="alert">{error}</p>}
        {page && (
          <TrackList
            tracks={page.tracks}
            total={page.total}
            offset={page.offset}
            limit={PAGE_SIZE}
            playingId={playing?.id ?? null}
            onPlay={play}
            onPage={setOffset}
          />
        )}
      </div>
      <Player track={playing} onEnded={next} />
    </>
  )
}
