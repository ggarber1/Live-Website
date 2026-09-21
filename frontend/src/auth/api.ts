import { BASE, json } from '../http'

export class LoginError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Not through request(): a 401 here means "wrong password", not "go log in".
export async function login(password: string): Promise<void> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, ...json({ password }),
  })
  if (res.ok) return
  let message = res.statusText
  try {
    const body = await res.json()
    if (body && typeof body.error === 'string') message = body.error
  } catch {
    // not JSON
  }
  throw new LoginError(res.status, message)
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/api/auth/logout`, { method: 'POST' })
}
