import { useEffect, useState } from 'react'
import { Route, Routes } from 'react-router'

import { listFilms, type Film } from './api'
import FilmGrid from './FilmGrid'
import FilmPage from './FilmPage'

export default function CinemaPage() {
  return (
    <Routes>
      <Route index element={<FilmList />} />
      <Route path=":id" element={<FilmPage />} />
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
      {films && films.length > 0 && <FilmGrid films={films} />}
    </>
  )
}
