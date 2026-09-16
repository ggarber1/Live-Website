import { useCallback, useEffect, useState } from 'react'

import { listTracks, PAGE_SIZE, type Track, type TrackPage } from './api'
import { usePlayer } from './player-context'
import SearchBox from './SearchBox'
import TrackList from './TrackList'

export default function MusicPage() {
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<TrackPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { playing, play: playQueue } = usePlayer()

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
    playQueue(page.tracks, page.tracks.findIndex((t) => t.id === track.id))
  }

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
    </>
  )
}
