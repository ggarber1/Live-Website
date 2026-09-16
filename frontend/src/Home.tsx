import { Link } from 'react-router'

const SECTIONS = [
  { to: '/music', title: 'Music', blurb: 'Everything on the shelf, ready to play.' },
  { to: '/todo', title: 'To-do', blurb: 'Little things, crossed off one by one.' },
  { to: '/habits', title: 'Habits', blurb: 'Small promises, kept daily.' },
  { to: '/recipes', title: 'Recipes', blurb: 'The ones worth making again.' },
  { to: '/journal', title: 'Journal', blurb: 'A page for whatever today was.' },
]

export default function Home() {
  return (
    <>
      <h1>Hello, Liv.</h1>
      <p className="subtitle">Your little corner of the house, kept tidy.</p>
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
