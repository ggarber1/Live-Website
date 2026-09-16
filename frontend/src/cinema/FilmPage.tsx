import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'

import { formatDuration, formatRuntime } from '../format'
import { BASE } from '../http'
import { usePlayer } from '../music/player-context'
import { paragraphs } from '../text'
import { getFilm, play as requestPlay, posterUrl, savePosition, stop, type Film, type Playback } from './api'
import VideoPlayer from './VideoPlayer'

export default function FilmPage() {
  const id = useParams().id!
  const music = usePlayer()
  const [film, setFilm] = useState<Film | null>(null)
  // Kept with the id it belongs to, so moving to another film derives a
  // fresh page instead of resetting state in an effect.
  const [started, setStarted] = useState<{ id: string; playback: Playback; startAt: number } | null>(null)
  const current = started?.id === id ? started : null
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getFilm(id).then(setFilm, (err: Error) => setError(err.message))
  }, [id])

  const play = async (startAt: number) => {
    setBusy(true)
    setError(null)
    music.pause()
    try {
      setStarted({ id, playback: await requestPlay(id), startAt })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!film) return error ? <p role="alert">{error}</p> : null

  const meta = [film.year, formatRuntime(film.runtime_seconds)].filter(Boolean).join(' · ')
  // Under half a minute in is not worth offering; neither is a finished film.
  const resumable = film.position_seconds > 30 && !film.played

  return (
    <>
      <p className="crumb"><Link to="/cinema">Cinema</Link></p>
      <div className="film-hero" style={{ backgroundImage: `url(${BASE}/api/cinema/films/${film.id}/backdrop)` }}>
        <div className="film-hero-fade">
          <h1>{film.title}</h1>
          {meta && <p className="subtitle">{meta}</p>}
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      {current ? (
        <VideoPlayer
          kind={current.playback.kind}
          url={current.playback.url}
          startAt={current.startAt}
          onStop={() => stop(current.playback.play_session_id)}
          onProgress={(seconds, finished) => savePosition(id, seconds, finished)}
        />
      ) : (
        <div className="film-body">
          {film.has_poster && <img className="poster" src={posterUrl(film.id, 400)} alt={`${film.title} poster`} />}
          <div className="film-about">
            {film.genres.length > 0 && <p className="describe">{film.genres.join(' · ')}</p>}
            {paragraphs(film.overview).map((text, i) => <p key={i}>{text}</p>)}
            <div className="actions">
              {resumable ? (
                <>
                  <button type="button" className="btn btn-primary" onClick={() => play(film.position_seconds)} disabled={busy}>
                    Resume from {formatDuration(film.position_seconds)}
                  </button>
                  <button type="button" className="btn" onClick={() => play(0)} disabled={busy}>Start over</button>
                </>
              ) : (
                <button type="button" className="btn btn-primary" onClick={() => play(0)} disabled={busy}>Play</button>
              )}
              {film.playback === 'transcode' && (
                <em className="note">will transcode: the Pi may struggle with this one</em>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
