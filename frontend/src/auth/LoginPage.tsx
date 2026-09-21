import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'

import { login, LoginError } from './api'
import { safeNext } from './next'

export default function LoginPage() {
  const [params] = useSearchParams()
  const [password, setPassword] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setProblem(null)
    try {
      await login(password)
      // A full navigation, not the router: the cookie is now set and every
      // page should start fresh with it.
      window.location.assign(safeNext(params.get('next')))
    } catch (err) {
      const status = err instanceof LoginError ? err.status : 0
      if (status === 429) setProblem('Too many tries. Give it half a minute.')
      else if (status === 401) setProblem("That's not it.")
      else setProblem((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <form className="card login-card" onSubmit={submit}>
        <p className="site-name">Liv's <span className="ornament" aria-hidden="true">❦</span></p>
        <h1>It's you, isn't it?</h1>
        {problem && <p role="alert">{problem}</p>}
        <label>
          <span className="label">Password</span>
          <input
            className="field"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <div className="actions">
          <button type="submit" className="btn btn-primary" disabled={busy || !password}>Come in</button>
        </div>
      </form>
    </main>
  )
}
