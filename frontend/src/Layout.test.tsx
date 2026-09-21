import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'

import { logout } from './auth/api'
import Layout from './Layout'

vi.mock('./auth/api', () => ({ logout: vi.fn().mockResolvedValue(undefined) }))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="*" element={<p>page body</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

test('the nav links to every section', () => {
  renderAt('/')

  const nav = screen.getByRole('navigation')
  const hrefs = Array.from(nav.querySelectorAll('a')).map((a) => [a.textContent, a.getAttribute('href')])
  expect(hrefs).toEqual([
    ['Music', '/music'],
    ['Cinema', '/cinema'],
    ['Photos', '/photos'],
    ['To-do', '/todo'],
    ['Habits', '/habits'],
    ['Recipes', '/recipes'],
    ['Blog', '/blog'],
  ])
})

test('the current section is marked', () => {
  renderAt('/recipes/3')

  expect(screen.getByRole('link', { name: 'Recipes' })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('link', { name: 'Music' })).not.toHaveAttribute('aria-current')
})

test('the site name links home and renders the page body', () => {
  renderAt('/todo')

  expect(screen.getByRole('link', { name: /Liv/ })).toHaveAttribute('href', '/')
  expect(screen.getByText('page body')).toBeInTheDocument()
})

test('log out posts, then goes to the login page', async () => {
  const assign = vi.fn()
  vi.stubGlobal('location', { pathname: '/todo', search: '', assign })
  renderAt('/todo')

  await userEvent.click(screen.getByRole('button', { name: /log out/i }))

  expect(logout).toHaveBeenCalledTimes(1)
  await vi.waitFor(() => expect(assign).toHaveBeenCalledWith('/login'))
  vi.unstubAllGlobals()
})
