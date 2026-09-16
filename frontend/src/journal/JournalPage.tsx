import { useEffect, useState } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router'

import { formatDate } from '../format'
import { createPost, getPost, listPosts, updatePost, type Post, type PostDraft } from './api'
import PostForm from './PostForm'
import PostPage from './PostPage'
import { excerpt } from './text'

export default function JournalPage() {
  return (
    <Routes>
      <Route index element={<EntryList />} />
      <Route path="new" element={<NewEntry />} />
      <Route path=":id" element={<PostPage />} />
      <Route path=":id/edit" element={<EditEntry />} />
    </Routes>
  )
}

function EntryList() {
  const [posts, setPosts] = useState<Post[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listPosts().then(setPosts, (err: Error) => setError(err.message))
  }, [])

  return (
    <>
      <div className="title-row">
        <div>
          <h1>Journal</h1>
          <p className="subtitle">A page for whatever today was.</p>
        </div>
        <Link to="/journal/new" className="btn btn-primary">Write</Link>
      </div>
      {error && <p role="alert">{error}</p>}
      {posts && posts.length === 0 && <p className="empty">Nothing written yet.</p>}
      {posts && posts.length > 0 && (
        <div className="stack">
          {posts.map((post) => (
            <Link key={post.id} to={`/journal/${post.id}`} className="card card-link">
              <h2>{post.title}</h2>
              <p className="date">{formatDate(post.created_at)}</p>
              <p className="excerpt">{excerpt(post.content)}</p>
            </Link>
          ))}
        </div>
      )}
    </>
  )
}

function NewEntry() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const save = async (draft: PostDraft) => {
    setBusy(true)
    try {
      const id = await createPost(draft)
      navigate(`/journal/${id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <>
      <p className="crumb"><Link to="/journal">Journal</Link></p>
      <h1>New entry</h1>
      <p className="subtitle">However today went.</p>
      {error && <p role="alert">{error}</p>}
      <div className="card">
        <PostForm onSubmit={save} busy={busy} />
      </div>
    </>
  )
}

function EditEntry() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const [post, setPost] = useState<Post | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getPost(id).then(setPost, (err: Error) => setError(err.message))
  }, [id])

  const save = async (draft: PostDraft) => {
    setBusy(true)
    try {
      await updatePost(id, draft)
      navigate(`/journal/${id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <>
      <p className="crumb"><Link to={`/journal/${id}`}>{post?.title ?? 'Entry'}</Link></p>
      <h1>Edit entry</h1>
      {error && <p role="alert">{error}</p>}
      {post && (
        <div className="card">
          <PostForm initial={post} onSubmit={save} busy={busy} />
        </div>
      )}
    </>
  )
}
