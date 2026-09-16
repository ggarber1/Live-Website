import { useEffect, useState } from 'react'
import { Link, Route, Routes, useParams } from 'react-router'

import { listFilms, play, stop, type Film, type Playback } from './api'
import VideoPlayer from './VideoPlayer'

// Temporary shape for the end-to-end checkpoint: a list of titles and a
// player. The grid and film page replace this in the next task.
export default function CinemaPage() {
  return (
    <Routes>
      <Route index element={<FilmList />} />
      <Route path=":id" element={<FilmPlay />} />
    </Routes>
  )
}

function FilmList() {
  const [films, setFilms] = useState<Film[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listFilms().then(setFilms, (err: Error) => setError(err.message))
  }, [])

  return (
    <>
      <h1>Cinema</h1>
      <p className="subtitle">Something to watch tonight.</p>
      {error && <p role="alert">{error}</p>}
      {films && films.length === 0 && <p className="empty">No films yet.</p>}
      {films && films.length > 0 && (
        <ul>
          {films.map((film) => (
            <li key={film.id}>
              <Link to={`/cinema/${film.id}`}>{film.title}</Link>
              {film.year && ` (${film.year})`}
              {film.playback === 'transcode' && <em> — will transcode</em>}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function FilmPlay() {
  const id = useParams().id!
  const [playback, setPlayback] = useState<Playback | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    play(id).then(setPlayback, (err: Error) => setError(err.message))
  }, [id])

  return (
    <>
      <p className="crumb"><Link to="/cinema">Cinema</Link></p>
      {error && <p role="alert">{error}</p>}
      {playback && (
        <VideoPlayer kind={playback.kind} url={playback.url} onStop={() => stop(playback.play_session_id)} />
      )}
    </>
  )
}
