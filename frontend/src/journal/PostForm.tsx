import { useState, type FormEvent } from 'react'

import type { PostDraft } from './api'

interface Props {
  initial?: PostDraft
  onSubmit: (draft: PostDraft) => void
  busy?: boolean
}

export default function PostForm({ initial, onSubmit, busy = false }: Props) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [content, setContent] = useState(initial?.content ?? '')
  const [problem, setProblem] = useState<string | null>(null)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !content.trim()) {
      setProblem('An entry needs a title and something written.')
      return
    }
    setProblem(null)
    onSubmit({ title: title.trim(), content: content.trim() })
  }

  return (
    <form className="stack" onSubmit={submit}>
      {problem && <p role="alert">{problem}</p>}
      <label>
        <span className="label">Title</span>
        <input className="field" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        <span className="label">Entry <em>blank line between paragraphs</em></span>
        <textarea className="field" rows={12} value={content} onChange={(e) => setContent(e.target.value)} />
      </label>
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>Save</button>
      </div>
    </form>
  )
}
