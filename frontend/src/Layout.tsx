import { Link, NavLink, Outlet } from 'react-router'

const SECTIONS: [string, string][] = [
  ['Music', '/music'],
  ['To-do', '/todo'],
  ['Habits', '/habits'],
  ['Recipes', '/recipes'],
  ['Journal', '/journal'],
]

export default function Layout() {
  return (
    <>
      <header className="masthead">
        <Link to="/" className="site-name">
          Liv's <span className="ornament" aria-hidden="true">❦</span>
        </Link>
        <nav aria-label="Sections">
          {SECTIONS.map(([label, to]) => (
            <NavLink key={to} to={to}>{label}</NavLink>
          ))}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </>
  )
}
