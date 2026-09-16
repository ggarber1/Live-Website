import { BrowserRouter, Route, Routes } from 'react-router'

import HabitsPage from './habits/HabitsPage'
import Home from './Home'
import BlogPage from './blog/BlogPage'
import CinemaPage from './cinema/CinemaPage'
import Layout from './Layout'
import MusicPage from './music/MusicPage'
import NotFound from './NotFound'
import PhotosPage from './photos/PhotosPage'
import RecipesPage from './recipes/RecipesPage'
import TodoPage from './todo/TodoPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="music" element={<MusicPage />} />
          <Route path="cinema/*" element={<CinemaPage />} />
          <Route path="photos" element={<PhotosPage />} />
          <Route path="todo" element={<TodoPage />} />
          <Route path="habits" element={<HabitsPage />} />
          <Route path="recipes/*" element={<RecipesPage />} />
          <Route path="blog/*" element={<BlogPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
