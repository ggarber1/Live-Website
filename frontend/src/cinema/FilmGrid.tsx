import { Link } from 'react-router'

import { posterUrl, type Film } from './api'

interface Props {
  films: Film[]
}

export default function FilmGrid({ films }: Props) {
  return (
    <div className="film-grid">
      {films.map((film) => (
        <Link key={film.id} to={`/cinema/${film.id}`} className="film-card">
          {film.has_poster ? (
            <img className="poster" src={posterUrl(film.id, 300)} alt={`${film.title} poster`} loading="lazy" />
          ) : (
            <div className="poster placeholder" aria-hidden="true">❦</div>
          )}
          <div className="film-title">{film.title}</div>
          <div className="describe">
            {film.year && <span>{film.year}</span>}
            {film.playback === 'transcode' && <em className="note">will transcode</em>}
          </div>
        </Link>
      ))}
    </div>
  )
}
