import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { dateLine, nextGreeting, noteOfTheDay } from './greeting'
import { listPhotos, type Photo } from './photos/api'
import Polaroid from './photos/Polaroid'

const TILTS = [-1.5, 1, -0.5, 1.5, -1, 0.5]

const SECTIONS = [
  { to: '/music', title: 'Music', blurb: "Let's Partayyy" },
  { to: '/cinema', title: 'Cinema', blurb: 'Movie Night!!!' },
  { to: '/photos', title: 'Photos', blurb: "Let's go down memory lane" },
  { to: '/todo', title: 'To-do', blurb: 'Get Shit Done' },
  { to: '/habits', title: 'Habits', blurb: "Okay, She's Consistent" },
  { to: '/recipes', title: 'Recipes', blurb: 'Yummmmmmm' },
  { to: '/blog', title: 'Blog', blurb: 'Hey guys Welcome to my Story' },
]

export default function Home() {
  const now = new Date()
  // Chosen once per visit, not per render, so it does not change under her.
  const [hello] = useState(() => nextGreeting(now))
  const [photos, setPhotos] = useState<Photo[]>([])

  // The newest few, as prints on the counter. A failure here is not the home
  // page's problem: the band simply does not appear.
  useEffect(() => {
    listPhotos({ limit: 6 }).then((page) => setPhotos(page.photos), () => {})
  }, [])

  return (
    <>
      <div className="hello">
        <h1>{hello} <span className="ornament" aria-hidden="true">❦</span></h1>
        <p className="subtitle">{[dateLine(now), noteOfTheDay(now)].filter(Boolean).join(' ')}</p>
      </div>
      {photos.length > 0 && (
        <section className="photo-band" aria-label="Recent photos">
          <div className="photo-band-row">
            {photos.map((photo, i) => (
              <Link key={photo.id} to="/photos" className="polaroid-link">
                <Polaroid photo={photo} tilt={TILTS[i % TILTS.length]} />
              </Link>
            ))}
          </div>
          <p className="photo-band-more"><Link to="/photos">All photos ❦</Link></p>
        </section>
      )}
      <div className="card-grid">
        {SECTIONS.map(({ to, title, blurb }) => (
          <Link key={to} to={to} className="card card-link">
            <h2>{title}</h2>
            <p>{blurb}</p>
          </Link>
        ))}
      </div>
    </>
  )
}
