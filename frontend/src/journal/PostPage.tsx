import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { formatDate } from '../format'
import { getPost, removePost, type Post } from './api'
import { paragraphs } from './text'

export default function PostPage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const [post, setPost] = useState<Post | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getPost(id).then(setPost, (err: Error) => setError(err.message))
  }, [id])

  const remove = async () => {
    if (!post || !confirm(`Delete "${post.title}"?`)) return
    try {
      await removePost(post.id)
      navigate('/journal')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (error) return <p role="alert">{error}</p>
  if (!post) return null

  return (
    <>
      <p className="crumb"><Link to="/journal">Journal</Link></p>
      <h1>{post.title}</h1>
      <p className="subtitle">{formatDate(post.created_at)}</p>
      <article className="entry">
        {paragraphs(post.content).map((text, i) => <p key={i}>{text}</p>)}
      </article>
      <div className="actions">
        <Link to={`/journal/${post.id}/edit`} className="btn">Edit</Link>
        <button type="button" className="btn btn-danger" onClick={remove}>Delete</button>
      </div>
    </>
  )
}
