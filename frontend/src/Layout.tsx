import { Link, NavLink, Outlet } from 'react-router'

import { logout } from './auth/api'

import { PlayerProvider } from './music/queue'

const SECTIONS: [string, string][] = [
  ['Music', '/music'],
  ['Cinema', '/cinema'],
  ['Photos', '/photos'],
  ['To-do', '/todo'],
  ['Habits', '/habits'],
  ['Recipes', '/recipes'],
  ['Blog', '/blog'],
]

export default function Layout() {
  return (
    <PlayerProvider>
      <header className="masthead">
        <Link to="/" className="site-name">
          Liv's <span className="ornament" aria-hidden="true">❦</span>
        </Link>
        <nav aria-label="Sections">
          {SECTIONS.map(([label, to]) => (
            <NavLink key={to} to={to}>{label}</NavLink>
          ))}
          <button
            type="button"
            className="nav-quiet"
            onClick={() => logout().then(() => window.location.assign('/login'))}
          >
            log out
          </button>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </PlayerProvider>
  )
}
