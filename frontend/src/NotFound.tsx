import { Link } from 'react-router'

export default function NotFound() {
  return (
    <>
      <h1>Not found</h1>
      <p className="subtitle">There's no page here. <Link to="/">Back home</Link>?</p>
    </>
  )
}
